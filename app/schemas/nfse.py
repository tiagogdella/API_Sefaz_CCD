from pydantic import BaseModel, ConfigDict, Field, field_validator


class NFSeQueryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    access_key: str = Field(alias="accessKey")

    @field_validator("access_key")
    @classmethod
    def validate_access_key(cls, value: str) -> str:
        if not (value.isdigit() and len(value) == 50):
            raise ValueError(
                "access_key must have exactly 50 numeric digits (NFS-e access key) "
                "(looks like this might be an NF-e/CT-e key, which has 44 digits - "
                "use /consultas/xml or /consultas/cte/xml instead)"
            )
        return value
