from datetime import datetime
from typing import ClassVar, Self

from pydantic import BaseModel, model_validator


class DateTimeRangeMixin(BaseModel):
    datetime_range_fields: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="after")
    def validate_datetime_ranges(self) -> Self:
        for field_name in self.datetime_range_fields:
            date_from: datetime | None = getattr(
                self,
                f"{field_name}_from",
                None,
            )
            date_to: datetime | None = getattr(
                self,
                f"{field_name}_to",
                None,
            )

            if date_from is not None and date_to is not None and date_from > date_to:
                raise ValueError(
                    f"{field_name}_from must be earlier than or equal"
                    f" to {field_name}_to"
                )

        return self
