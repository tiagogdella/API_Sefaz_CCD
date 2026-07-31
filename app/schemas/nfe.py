from pydantic import BaseModel, ConfigDict, Field, field_validator

class NFeQueryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    access_key: str = Field(alias="accessKey")

    @field_validator("access_key")
    @classmethod
    def validate_access_key(cls, value: str) -> str:
        if not (value.isdigit() and len(value) == 44):
            raise ValueError("access_key must have exactly 44 numeric digits")
        return value

class NFeQueryResponse(BaseModel):
    c_stat: str
    x_motivo: str