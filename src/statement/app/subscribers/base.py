from enum import StrEnum

from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue
from faststream.rabbit.schemas.queue import ClassicQueueArgs

from statement.conf import settings


class Exchanges(StrEnum):
    COMMANDS = "commands"
    COMMANDS_DLX = "commands.dlx"
    EVENTS = "events"
    EVENTS_DLX = "events.dlx"


class Queues(StrEnum):
    COMMANDS_DLQ = "commands.dlq"
    EVENTS_DLQ = "events.dlq"


commands_exchange = RabbitExchange(
    Exchanges.COMMANDS,
    type=ExchangeType.DIRECT,
    durable=True,
)
commands_dlx = RabbitExchange(
    Exchanges.COMMANDS_DLX,
    type=ExchangeType.FANOUT,
    durable=True,
)
commands_dlq = RabbitQueue(
    Queues.COMMANDS_DLQ,
    durable=True,
)

events_exchange = RabbitExchange(
    Exchanges.EVENTS,
    type=ExchangeType.TOPIC,
    durable=True,
)
events_dlx = RabbitExchange(
    Exchanges.EVENTS_DLX,
    type=ExchangeType.FANOUT,
    durable=True,
)
events_dlq = RabbitQueue(
    Queues.EVENTS_DLQ,
    durable=True,
)


def build_broker() -> RabbitBroker:
    return RabbitBroker(
        settings.amqp_dsn,
        graceful_timeout=settings.amqp_graceful_timeout,
    )


def live_queue(name: str, routing_key: str, dlx: str) -> RabbitQueue:
    args: ClassicQueueArgs = {
        "x-dead-letter-exchange": dlx,
        "x-dead-letter-routing-key": name,
    }

    return RabbitQueue(
        name,
        routing_key=routing_key,
        durable=True,
        arguments=args,
    )
