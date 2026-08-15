import logging
import logging.config

import structlog
from structlog.dev import ConsoleRenderer
from structlog.processors import JSONRenderer
from structlog.stdlib import ProcessorFormatter

from statement.conf import AppEnv, settings


def _add_service(service_name: str):
    def processor(logger, method_name, event_dict):
        event_dict["service"] = service_name
        return event_dict

    return processor


def build_shared_processors(service_name: str) -> list:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.UnicodeDecoder(),
        structlog.processors.CallsiteParameterAdder(
            {
                structlog.processors.CallsiteParameter.PATHNAME,
                structlog.processors.CallsiteParameter.QUAL_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            }
        ),
        _add_service(service_name),
    ]


if settings.app_env == AppEnv.LOCAL:
    renderer, exc_processors = ConsoleRenderer(), []
else:
    renderer, exc_processors = JSONRenderer(), [structlog.processors.format_exc_info]


def setup_logging(service_name: str) -> None:
    shared_processors = build_shared_processors(service_name)
    structlog.configure(
        processors=[
            *shared_processors,
            ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=settings.app_env != AppEnv.TEST,
    )

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processors": [
                        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                        *exc_processors,
                        renderer,
                    ],
                    "foreign_pre_chain": shared_processors,
                },
            },
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "default",
                    "level": settings.log_level,
                },
            },
            "root": {
                "handlers": ["stdout"],
                "level": settings.log_level,
            },
            "loggers": {
                "uvicorn": {"handlers": [], "propagate": True},
                "uvicorn.error": {"handlers": [], "propagate": True},
                "uvicorn.access": {"handlers": [], "propagate": True},
                "faststream": {"handlers": [], "propagate": True},
            },
        }
    )
