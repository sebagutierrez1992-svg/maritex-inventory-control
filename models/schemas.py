from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class SourceMetadata:
    filename: str
    loaded_at: datetime
    rows: int = 0
    min_date: Optional[str] = None
    max_date: Optional[str] = None
    amount_column: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class SalesFilter:
    month: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    sellers: tuple[str, ...] = ()
    warehouses: tuple[str, ...] = ()
    document_types: tuple[str, ...] = ()
    client: str = ""
    include_vat: bool = True
