#!/bin/bash
#
# This script is run inside the Docker container to check that we're running the latest container
# and warn if we aren't, then kick off running the link checker tool.

function get_tag_for_latest(){
    LATEST_ALIAS=""
    # From https://stackoverflow.com/a/41830007/1233830
    REPOSITORY="linaroits/linkcheck"
    TARGET_TAG="latest"
    # check that we have Internet access - bail quickly if we don't
    curl -Is "https://auth.docker.io" >/dev/null 2>&1 || return $?
    # get authorization token
    TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:$REPOSITORY:pull" | jq -r .token) || return $?
    # find all tags
    ALL_TAGS=$(curl -s -H "Authorization: Bearer $TOKEN" https://index.docker.io/v2/$REPOSITORY/tags/list | jq -r .tags[]) || return $?
    # get image digest for target
    TARGET_DIGEST=$(curl -s -D - -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.docker.distribution.manifest.v2+json" https://index.docker.io/v2/$REPOSITORY/manifests/$TARGET_TAG | grep Docker-Content-Digest | cut -d ' ' -f 2) || return $?
    # Iterate through the tags, but we need to use unquoted bash expansion so turn off the shellcheck warning
    # shellcheck disable=SC2068
    for tag in ${ALL_TAGS[@]}; do
        # get image digest
        digest=$(curl -s -D - -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.docker.distribution.manifest.v2+json" "https://index.docker.io/v2/$REPOSITORY/manifests/$tag" | grep Docker-Content-Digest | cut -d ' ' -f 2) || return $?
        # check digest
        if [ "$TARGET_DIGEST" = "$digest" ] && [ "$tag" != "$TARGET_TAG" ]; then
            LATEST_ALIAS="$tag"
        fi
    done
}

# The "external" script will mount the source directory under /srv so we check against that.
cd "/app" || exit
/app/main.py "$@"
