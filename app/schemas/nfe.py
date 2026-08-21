from pydantic import BaseModel, ConfigDict, Field, field_validator

class NFeQueryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    access_key: str = Field(alias="accessKey")

    @field_validator("access_key")
    @classmethod
    def validate_access_key(cls, value: str) -> str:
        if not (value.isdigit() and len(value) == 44):
            raise ValueError("access_key must have exactly 44 numeric digits")

        model = value[20:22]  # posicoes 21-22 (1-indexed) da chave
        if model not in ("55", "65"):
            raise ValueError(
                f"access_key model must be 55 (NF-e) or 65 (NFC-e), got {model} "
                "(looks like this might be a CT-e key — use /consultas/cte/xml instead)"
            )

        return value

class NFeQueryResponse(BaseModel):
    c_stat: str
    x_motivo: str

class NfeItem(BaseModel):
    code: str
    description: str
    quantity: float
    unit: str
    unit_price: float
    total_price: float


class NfeParsed(BaseModel):
    access_key: str
    invoice_number: str
    supplier_cnpj: str
    supplier_name: str
    issue_date: str
    total_amount: float
    items: list[NfeItem]
    certificate_profile: str
