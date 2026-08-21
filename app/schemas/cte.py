from pydantic import BaseModel, ConfigDict, Field, field_validator


class CTeQueryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    access_key: str = Field(alias="accessKey")

    @field_validator("access_key")
    @classmethod
    def validate_access_key(cls, value: str) -> str:
        if not (value.isdigit() and len(value) == 44):
            raise ValueError("access_key must have exactly 44 numeric digits")

        model = value[20:22]  # posicoes 21-22 (1-indexed) da chave
        if model not in ("57", "67"):
            raise ValueError(
                f"access_key model must be 57 (CT-e) or 67 (CT-e OS), got {model} "
                "(looks like this might be an NF-e key — use /consultas/xml instead)"
            )

        return value
