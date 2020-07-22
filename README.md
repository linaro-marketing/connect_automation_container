# connect_automation_container

This is the repo for the Connect Automation Container (Docker). Built for Ubuntu Linux, but may work on other platforms if you modify the passed UID and GID in the [Usage instructions](#Usage).

## Prerequisites

[Docker](https://www.docker.com/)

## Building

Build with e.g:

```zsh
docker build\
 --rm\
 -t\
 "linaroits/connect-automation:$( git rev-parse --short HEAD )" .
```

Build locally for dev:

```zsh
docker build --no-cache --rm -t "connect_automation" .
```

## Usage

### Environment variables

Before using, the following environment variables must be set:

- `bamboo_sched_password`
- `bamboo_sched_url`
- `bamboo_connect_uid`
- `bamboo_working_directory`
- `bamboo_s3_session_id`

The Sched API key can be found at `https://EVENT_CODE.sched.com/editor/exports/api`

Run with e.g:

```zsh
docker run\
 --cap-drop=all\
 --rm\
 -i\
 -t\
 -u=$(id -u):$(id -g)\
 --name connect-automation-container\
 "linaroits/connect-automation:$( git rev-parse --short HEAD )"\
 /app/main.py
```
Running locally for development:

Make sure to have the correct AWS credentials in Environment variables. You can get these from the the Linaro AWS SSO portal. Current using the Dev Account.

```zsh
export AWS_ACCESS_KEY_ID="xxxxxxxxxxx"
export AWS_SECRET_ACCESS_KEY="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export AWS_SESSION_TOKEN="xxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

Running the built `connect_automation` container.

```zsh
docker run \
    --cap-drop=all \
    --memory=1GB \
   -it \
   --rm \
   -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
   -e AWS_SESSION_TOKEN=$AWS_SESSION_TOKEN  -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
   -e bamboo_github_access_password="GITHUB_API_KEY_FOR_CREATING_PULLS" -e bamboo_sched_url="https://lvc20.sched.com" \
   -e bamboo_s3_session_id="LVC20-101" \
   -e bamboo_event_key='["LVC20-101"]' \
   -e bamboo_sched_password="SCHED_API_KEY" \
   -e bamboo_connect_uid="LVC20" \
   -e bamboo_working_directory="/app/work_dir" \
   -v `pwd`/work_dir:/app/work_dir \
   connect_automation /app/main.py

```
