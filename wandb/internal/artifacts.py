import json
import os
import tempfile

from wandb.interface.artifacts import ArtifactManifest
import wandb.filesync.step_prepare


def _manifest_json_from_proto(manifest):
    if manifest.version == 1:
        contents = {
            content.path: {
                "digest": content.digest,
                "birthArtifactID": content.birth_artifact_id
                if content.birth_artifact_id
                else None,
                "ref": content.ref if content.ref else None,
                "size": content.size if content.size is not None else None,
                "local_path": content.local_path if content.local_path else None,
                "extra": {
                    extra.key: json.loads(extra.value_json) for extra in content.extra
                },
            }
            for content in manifest.contents
        }
    else:
        raise Exception(
            "unknown artifact manifest version: {}".format(manifest.version)
        )

    return {
        "version": manifest.version,
        "storagePolicy": manifest.storage_policy,
        "storagePolicyConfig": {
            config.key: json.loads(config.value_json)
            for config in manifest.storage_policy_config
        },
        "contents": contents,
    }


class ArtifactSaver(object):
    def __init__(self, api, digest, manifest_json, file_pusher, is_user_created=False):
        self._api = api
        self._file_pusher = file_pusher
        self._digest = digest
        self._manifest = ArtifactManifest.from_manifest_json(None, manifest_json)
        self._is_user_created = is_user_created
        self._server_artifact = None

    def save(
        self,
        type,
        name,
        metadata=None,
        description=None,
        aliases=None,
        labels=None,
        use_after_commit=False,
    ):
        aliases = aliases or []
        alias_specs = []
        for alias in aliases:
            if ":" in alias:
                # Users can explicitly alias this artifact to names
                # other than the primary one passed in by using the
                # 'secondaryName:alias' notation.
                idx = alias.index(":")
                artifact_collection_name = alias[: idx - 1]
                tag = alias[idx + 1 :]
            else:
                artifact_collection_name = name
                tag = alias
            alias_specs.append(
                {"artifactCollectionName": artifact_collection_name, "alias": tag,}
            )

        """Returns the server artifact."""
        self._server_artifact, latest = self._api.create_artifact(
            type,
            name,
            self._digest,
            metadata=metadata,
            aliases=alias_specs,
            labels=labels,
            description=description,
            is_user_created=self._is_user_created,
        )

        # TODO(artifacts):
        #   if it's committed, all is good. If it's committing, just moving ahead isn't necessarily
        #   correct. It may be better to poll until it's committed or failed, and then decided what to
        #   do
        artifact_id = self._server_artifact["id"]
        latest_artifact_id = latest["id"] if latest else None
        if (
            self._server_artifact["state"] == "COMMITTED"
            or self._server_artifact["state"] == "COMMITTING"
        ):
            # TODO: update aliases, labels, description etc?
            if use_after_commit:
                self._api.use_artifact(artifact_id)
            return self._server_artifact
        elif (
            self._server_artifact["state"] != "PENDING"
            and self._server_artifact["state"] != "DELETED"
        ):
            raise Exception(
                'Unknown artifact state "{}"'.format(self._server_artifact["state"])
            )

        self._api.create_artifact_manifest(
            "wandb_manifest.json",
            "",
            artifact_id,
            base_artifact_id=latest_artifact_id,
            include_upload=False,
        )

        step_prepare = wandb.filesync.step_prepare.StepPrepare(
            self._api, 0.1, 0.01, 1000
        )  # TODO: params
        step_prepare.start()

        # Upload Artifact "L1" files, the actual artifact contents
        self._file_pusher.store_manifest_files(
            self._manifest,
            artifact_id,
            lambda entry, progress_callback: self._manifest.storage_policy.store_file(
                artifact_id, entry, step_prepare, progress_callback=progress_callback
            ),
        )

        def before_commit():
            with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as fp:
                path = os.path.abspath(fp.name)
                json.dump(self._manifest.to_manifest_json(), fp, indent=4)
            digest = wandb.util.md5_file(path)
            # We're duplicating the file upload logic a little, which isn't great.
            resp = self._api.create_artifact_manifest(
                "wandb_manifest.json",
                digest,
                artifact_id,
                base_artifact_id=latest_artifact_id,
            )
            upload_url = resp["uploadUrl"]
            upload_headers = resp["uploadHeaders"]
            extra_headers = {}
            for upload_header in upload_headers:
                key, val = upload_header.split(":", 1)
                extra_headers[key] = val
            with open(path, "rb") as fp:
                self._api.upload_file_retry(upload_url, fp, extra_headers=extra_headers)

        def on_commit():
            if use_after_commit:
                self._api.use_artifact(artifact_id)
            step_prepare.shutdown()

        # This will queue the commit. It will only happen after all the file uploads are done
        self._file_pusher.commit_artifact(
            artifact_id, before_commit=before_commit, on_commit=on_commit
        )
        return self._server_artifact
