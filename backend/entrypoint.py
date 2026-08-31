#!/usr/bin/env python3
"""Container entrypoint: load secrets from SSM Parameter Store, then exec the app.

Why this exists
---------------
Secrets must never be baked into the image or written to a .env file on the
host. Instead the EC2 instance carries an IAM role, this script uses that role
to read SecureString parameters out of SSM Parameter Store at container start,
injects them into the process environment, and then exec's the real command.

Because it uses exec (not a subprocess), gunicorn replaces this process and
becomes PID 1, so Docker's stop signals reach it directly.

Local development
-----------------
If AIDOCTOR_SSM_PATH is unset, this script does nothing but exec the command,
and the app falls back to reading backend/.env through python-dotenv as before.
That keeps `docker compose up` working on a laptop with no AWS credentials.

Parameter naming
----------------
Every parameter under the configured path becomes an environment variable named
after its last path segment, uppercased. For example:

    /aidoctor/prod/OPENROUTER_API_KEY  ->  OPENROUTER_API_KEY
    /aidoctor/prod/PINECONE_API_KEY    ->  PINECONE_API_KEY
"""

import os
import sys

SSM_PATH_VAR = "AIDOCTOR_SSM_PATH"


def _region_from_imds() -> str | None:
    """Ask the EC2 instance metadata service which region we are in.

    Last-resort fallback so the container works even when no region variable
    was passed in. Uses IMDSv2 (token first), which is required on instances
    configured with HttpTokens=required.
    """
    import json
    import urllib.request

    try:
        token = urllib.request.urlopen(
            urllib.request.Request(
                "http://169.254.169.254/latest/api/token",
                method="PUT",
                headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
            ),
            timeout=2,
        ).read().decode()

        doc = urllib.request.urlopen(
            urllib.request.Request(
                "http://169.254.169.254/latest/dynamic/instance-identity/document",
                headers={"X-aws-ec2-metadata-token": token},
            ),
            timeout=2,
        )
        return json.load(doc).get("region")
    except Exception:
        return None


def resolve_region() -> str | None:
    """Find the AWS region to use.

    botocore only reads AWS_DEFAULT_REGION from the environment -- AWS_REGION
    (which the other AWS SDKs honour) is ignored, and boto3 then fails with
    "You must specify a region". Check both, then fall back to instance metadata.
    """
    return (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or _region_from_imds()
    )


def load_ssm_parameters(path: str) -> dict[str, str]:
    """Return every parameter under `path` as a NAME -> value mapping.

    Raises on failure. A container that cannot read its secrets must not start
    and quietly serve errors -- it should crash so the restart policy and your
    logs make the problem obvious.
    """
    import boto3  # imported lazily so local runs do not need boto3 configured

    if not path.endswith("/"):
        path += "/"

    region = resolve_region()
    if not region:
        raise RuntimeError(
            "no AWS region found. Set AWS_REGION in deploy.env, or check that "
            "the instance metadata service is reachable from the container."
        )

    print(f"entrypoint: using AWS region {region}", flush=True)
    client = boto3.client("ssm", region_name=region)
    paginator = client.get_paginator("get_parameters_by_path")

    values: dict[str, str] = {}
    for page in paginator.paginate(Path=path, Recursive=True, WithDecryption=True):
        for param in page["Parameters"]:
            name = param["Name"].rsplit("/", 1)[-1].upper()
            values[name] = param["Value"]

    return values


def main() -> None:
    command = sys.argv[1:]
    if not command:
        print("entrypoint: no command given", file=sys.stderr)
        raise SystemExit(2)

    ssm_path = os.environ.get(SSM_PATH_VAR)

    if ssm_path:
        print(f"entrypoint: loading secrets from SSM path {ssm_path}", flush=True)
        try:
            parameters = load_ssm_parameters(ssm_path)
        except Exception as exc:
            print(f"entrypoint: FATAL - could not read SSM parameters: {exc}", file=sys.stderr)
            raise SystemExit(1)

        if not parameters:
            print(
                f"entrypoint: FATAL - no parameters found under {ssm_path}. "
                "Check the path and the instance role's ssm:GetParametersByPath permission.",
                file=sys.stderr,
            )
            raise SystemExit(1)

        # Anything already set explicitly in the environment (for example
        # DATABASE_URL from docker-compose) wins over SSM, so compose stays the
        # single source of truth for non-secret wiring.
        injected = []
        for name, value in parameters.items():
            if name not in os.environ:
                os.environ[name] = value
                injected.append(name)

        # Log names only. Never log values.
        print(f"entrypoint: loaded {len(injected)} secret(s): {', '.join(sorted(injected))}", flush=True)
    else:
        print(
            f"entrypoint: {SSM_PATH_VAR} not set - skipping SSM, using local environment/.env",
            flush=True,
        )

    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
