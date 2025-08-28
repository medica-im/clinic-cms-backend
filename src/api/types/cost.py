from pydantic import BaseModel, Field

class CarteVitale(BaseModel):
    carte_vitale: bool|None = None