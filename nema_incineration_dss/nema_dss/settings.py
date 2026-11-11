from pathlib import Path
import os
from urllib.parse import parse_qs, unquote, urlsplit
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

VERCEL = any(
    os.getenv(variable)
    for variable in ("VERCEL", "VERCEL_ENV", "VERCEL_URL")
)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-secret-key")
DEBUG = (
    os.getenv("DEBUG", "False" if VERCEL else "True").lower() == "true"
    and not VERCEL
)


def get_allowed_hosts():
    hosts = [
        host.strip()
        for host in os.getenv(
            "ALLOWED_HOSTS", "127.0.0.1,localhost,nema-system.vercel.app"
        ).split(",")
        if host.strip()
    ]
    for variable in (
        "VERCEL_URL",
        "VERCEL_PROJECT_PRODUCTION_URL",
        "VERCEL_BRANCH_URL",
    ):
        value = os.getenv(variable)
        if value:
            hostname = urlsplit(
                value if "://" in value else f"//{value}"
            ).hostname
            if hostname:
                hosts.append(hostname)
    return list(dict.fromkeys(hosts))


ALLOWED_HOSTS = get_allowed_hosts()

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "nema_dss.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "core.context_processors.navigation_context",
    ]},
}]
WSGI_APPLICATION = "nema_dss.wsgi.application"
ASGI_APPLICATION = "nema_dss.asgi.application"

def postgres_database_from_url(database_url):
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL must use the postgres or postgresql scheme.")

    database_name = unquote(parsed.path.lstrip("/"))
    if not parsed.hostname or not database_name:
        raise ValueError("DATABASE_URL must include a database name and host.")

    database = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": database_name,
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname,
        "PORT": parsed.port or "5432",
    }
    query = parse_qs(parsed.query)
    options = {
        name: query[name][0]
        for name in ("sslmode", "channel_binding")
        if query.get(name)
    }
    if options:
        database["OPTIONS"] = options
    return database


DATABASE_URL = os.getenv("DATABASE_URL")
DB_ENGINE = os.getenv("DB_ENGINE", "sqlite").lower()
if DATABASE_URL:
    DATABASES = {"default": postgres_database_from_url(DATABASE_URL)}
elif DB_ENGINE == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "nema_dss"),
            "USER": os.getenv("DB_USER", "postgres"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }
elif DB_ENGINE == "sqlite":
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
else:
    raise ValueError("DB_ENGINE must be either 'sqlite' or 'postgresql'.")

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_ENDPOINT_URL_S3 = os.getenv("AWS_ENDPOINT_URL_S3", "")
AWS_REGION = os.getenv("AWS_REGION", "")
AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME", "nema-dss-files")
USE_OBJECT_STORAGE = all(
    value
    for value in (
        AWS_ACCESS_KEY_ID,
        AWS_SECRET_ACCESS_KEY,
        AWS_ENDPOINT_URL_S3,
        AWS_REGION,
    )
)
STORAGES = {
    "default": {
        "BACKEND": (
            "core.storage.NeonObjectStorage"
            if USE_OBJECT_STORAGE
            else "django.core.files.storage.FileSystemStorage"
        ),
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = Path(
    os.getenv("MEDIA_ROOT")
    or ("/tmp/nema-media" if VERCEL else BASE_DIR / "media")
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/login/"

CSRF_TRUSTED_ORIGINS = [x.strip() for x in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if x.strip()]
