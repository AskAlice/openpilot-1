"""Install exception handler for process crash."""
from selfdrive.swaglog import cloudlog
from selfdrive.version import get_version
import traceback
import datetime

import sentry_sdk
from sentry_sdk.integrations.threading import ThreadingIntegration

def capture_exception(*args, **kwargs) -> None:
  cloudlog.error("crash", exc_info=kwargs.get('exc_info', 1))

  try:
    with open('/data/log/last_exception', 'w') as f:
      now = datetime.datetime.now()
      f.write(now.strftime('[%Y-%m-%d %H:%M:%S]') + "\n\n" + str(traceback.format_exc()))
  except Exception:
    pass

  try:
    sentry_sdk.capture_exception(*args, **kwargs)
    sentry_sdk.flush()  # https://github.com/getsentry/sentry-python/issues/291
  except Exception:
    cloudlog.exception("sentry exception")

def bind_user(**kwargs) -> None:
  sentry_sdk.set_user(kwargs)

def bind_extra(**kwargs) -> None:
  for k, v in kwargs.items():
    sentry_sdk.set_tag(k, v)

def init() -> None:
  sentry_sdk.init("https://ea01cb7973b74884a015cef3f7829d86@o409002.ingest.sentry.io/5280713",
                  default_integrations=False, integrations=[ThreadingIntegration(propagate_hub=True)],
                  release=get_version())
