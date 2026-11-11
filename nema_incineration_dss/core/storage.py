from botocore.config import Config
from django.conf import settings
from django.core.files import File
from django.core.files.storage import Storage

import boto3
from botocore.exceptions import ClientError


class NeonObjectStorage(Storage):
    def __init__(self):
        self.bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.AWS_ENDPOINT_URL_S3,
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        )

    def _open(self, name, mode="rb"):
        response = self.client.get_object(Bucket=self.bucket_name, Key=name)
        return File(response["Body"], name=name)

    def _save(self, name, content):
        if hasattr(content, "seek"):
            content.seek(0)
        extra_args = {}
        content_type = getattr(content, "content_type", None)
        if content_type:
            extra_args["ContentType"] = content_type
        self.client.upload_fileobj(
            content,
            self.bucket_name,
            name,
            ExtraArgs=extra_args,
        )
        return name

    def delete(self, name):
        self.client.delete_object(Bucket=self.bucket_name, Key=name)

    def exists(self, name):
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=name)
        except ClientError as error:
            if error.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                return False
            raise
        return True

    def size(self, name):
        response = self.client.head_object(Bucket=self.bucket_name, Key=name)
        return response["ContentLength"]

    def url(self, name):
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket_name, "Key": name},
            ExpiresIn=3600,
        )
