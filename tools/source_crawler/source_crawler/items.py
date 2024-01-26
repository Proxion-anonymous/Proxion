# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class ContractItem:
    address: str
    public_name_tag: Optional[str] = None
    labels: list[str] = field(default_factory=list)
    verified: Optional[bool] = None
    similar_contract: Optional[str] = None
    contract_name: Optional[str] = None
    compiler_version: Optional[str] = None
    abi: Optional[str] = None

    # source_files is a dict of filename -> content for multiple source files
    source_files: dict[str, str] = field(default_factory=dict)

    # soruce_code is the combination of all source files by expanding imports
    source_code: Optional[str] = None

    errors: list = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"ContractItem(address={self.address}, "
            f"public_name_tag={self.public_name_tag}, "
            f"labels={self.labels}, "
            f"verified={self.verified}, "
            f"contract_name={self.contract_name}, "
            f"compiler_version={self.compiler_version}, "
            f"errors={self.errors})"
        )

    def asdict(self):
        return asdict(self)
