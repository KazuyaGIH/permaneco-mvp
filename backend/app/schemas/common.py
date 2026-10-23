from typing import Annotated

from pydantic import AfterValidator, StringConstraints


def validate_preferred_name(value: str) -> str:
    if not all(character.isalpha() or character in " '-" for character in value):
        raise ValueError("Use apenas letras, espaços, apóstrofo e hífen.")
    if not value.strip():
        raise ValueError("Informe um nome preferido.")
    return value


PreferredName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=40),
    AfterValidator(validate_preferred_name),
]
