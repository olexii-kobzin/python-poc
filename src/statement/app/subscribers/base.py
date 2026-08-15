from enum import StrEnum

from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue
from faststream.rabbit.schemas.queue import ClassicQueueArgs

from statement.conf import settings


class Exchanges(StrEnum):
    COMMANDS = "commands"
    COMMANDS_DLX = "commands.dlx"
    EVENTS = "events"
    EVENTS_DLX = "events.dlx"


commands_exchange = RabbitExchange(
    Exchanges.COMMANDS,
    type=ExchangeType.DIRECT,
    durable=True,
    arguments={"x-dead-letter-exchange": "dlx"},
)
commands_dlx = RabbitExchange(
    Exchanges.COMMANDS_DLX,
    type=ExchangeType.DIRECT,
    durable=True,
)

events_exchange = RabbitExchange(
    Exchanges.EVENTS,
    type=ExchangeType.TOPIC,
    durable=True,
    arguments={"x-dead-letter-exchange": "dlx"},
)
events_dlx = RabbitExchange(
    Exchanges.EVENTS_DLX,
    type=ExchangeType.TOPIC,
    durable=True,
)


def build_broker() -> RabbitBroker:
    return RabbitBroker(settings.amqp_dsn)


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
