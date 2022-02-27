import enum
import collections
import datetime
import csv
import logging
from typing                  import Optional, Generator, Tuple, Dict, List, Iterable
from cvm.parsing.util        import normalize_currency, normalize_quantity, date_from_string
from cvm.parsing.dfp.account import Account
from cvm.parsing.dfp.balance import Balance
from cvm.parsing.dfp         import bpa, dre

class Company:
    cnpj: str
    corporate_name: str
    cvm_code: str

    def __str__(self) -> str:
        return f'Company({ self.corporate_name } / CNPJ: { self.cnpj } / CVM: { self.cvm_code })'

class StatementGroup(enum.IntEnum):
    BPA = 1
    """Balanço Patrimonial Ativo"""
    
    BPP = 2
    """Balanço Patrimonial Passivo"""

    DRE = 3
    """Demonstração de Resultado"""

    DRA = 4
    """Demonstração de Resultado Abrangente"""

    DMPL = 5
    """Demonstração das Mutações do Patrimônio Líquido"""

    DFC_MD = 61
    """Demonstração de Fluxo de Caixa (Método Direto)"""

    DFC_MI = 62
    """Demonstração de Fluxo de Caixa (Método Indireto)"""

    DVA = 7
    """Demonstração de Valor Adicionado"""

class FiscalYearOrder(enum.Enum):
    LAST           = 'ÚLTIMO'
    SECOND_TO_LAST = 'PENÚLTIMO'

class Statement:
    version: int
    group: StatementGroup
    consolidated: bool
    company: Company
    currency: str
    accounts: list[Account]
    reference_date: datetime.date
    fiscal_year_start: Optional[datetime.date]
    fiscal_year_end: datetime.date
    fiscal_year_order: FiscalYearOrder

    def balance(self) -> Balance:
        if self.group == StatementGroup.BPA:
            return self._parse_balance(cls_list=(bpa.FinancialCompanyBalance, bpa.IndustrialCompanyBalance, bpa.InsuranceCompanyBalance))
        elif self.group == StatementGroup.DRE:
            return self._parse_balance(cls_list=(dre.IndustrialCompanyBalance,))

    def _parse_balance(self, cls_list) -> Balance:
        accounts_iter = iter(self.accounts)

        for cls in cls_list:
            try:
                return cls(accounts_iter)
            except ValueError:
                pass

        # TODO: specialize exception?
        raise ValueError('invalid/unknown balance layout')

class _RawStatement:
    __slots__ = [
        'reference_date',
        'version',
        'group',
        'cnpj',
        'corporate_name',
        'cvm_code',
        'currency_name',
        'currency_size',
        'fiscal_year_start',
        'fiscal_year_end',
        'fiscal_year_order',
        'accounts'
    ]

    reference_date: str
    version: str
    group: str
    cnpj: str
    corporate_name: str
    cvm_code: str
    currency_name: str
    currency_size: str
    fiscal_year_start: str
    fiscal_year_end: str
    fiscal_year_order: str
    accounts: List[Tuple[str, str, str, str]]

_stmt_groups_by_name = {
    'DF Consolidado - Balanço Patrimonial Ativo':                        (StatementGroup.BPA,    True),
    'DF Individual - Balanço Patrimonial Ativo':                         (StatementGroup.BPA,    False),
    'DF Consolidado - Balanço Patrimonial Passivo':                      (StatementGroup.BPP,    True),
    'DF Individual - Balanço Patrimonial Passivo':                       (StatementGroup.BPP,    False),
    'DF Consolidado - Demonstração do Resultado':                        (StatementGroup.DRE,    True),
    'DF Individual - Demonstração do Resultado':                         (StatementGroup.DRE,    False),
    'DF Consolidado - Demonstração de Resultado Abrangente':             (StatementGroup.DRA,    True),
    'DF Individual - Demonstração de Resultado Abrangente':              (StatementGroup.DRA,    False),
    'DF Consolidado - Demonstração do Fluxo de Caixa (Método Direto)':   (StatementGroup.DFC_MD, True),
    'DF Individual - Demonstração do Fluxo de Caixa (Método Direto)':    (StatementGroup.DFC_MD, False),
    'DF Consolidado - Demonstração do Fluxo de Caixa (Método Indireto)': (StatementGroup.DFC_MI, True),
    'DF Individual - Demonstração do Fluxo de Caixa (Método Indireto)':  (StatementGroup.DFC_MI, False),
    'DF Consolidado - Demonstração das Mutações do Patrimônio Líquido':  (StatementGroup.DMPL,   True),
    'DF Individual - Demonstração das Mutações do Patrimônio Líquido':   (StatementGroup.DMPL,   False),
    'DF Consolidado - Demonstração de Valor Adicionado':                 (StatementGroup.DVA,    True),
    'DF Individual - Demonstração de Valor Adicionado':                  (StatementGroup.DVA,    False)
}

def _read_statement_group(group: str) -> Tuple[StatementGroup, bool]:
    try:
        return _stmt_groups_by_name[group]
    except KeyError:
        raise ValueError(f"unknown DFP group '{ group }'") from None

def _read_raw_statements(csv_file, delimiter: str) -> Iterable[_RawStatement]:
    """Reads and returns DFP stmts as an iterable of `_RawStatement`s."""

    csv_reader = csv.DictReader(csv_file, delimiter=delimiter)

    stmts = {}
    prev_row = ''

    for row_index, row in enumerate(csv_reader):
        # Clean up duplicate rows. I don't know why, but some rows are duplicated.
        if row == prev_row:
            continue

        prev_row = row

        try:
            cvm_code        = row['CD_CVM']
            reference_date  = row['DT_REFER']
            fiscal_year_end = row['DT_FIM_EXERC']
        except KeyError as e:
            logging.warn('failed to read row %d: %s', row_index, e)
            continue

        stmt_key = cvm_code + reference_date + fiscal_year_end

        try:
            stmt = stmts[stmt_key]
        except KeyError:
            stmt = _RawStatement()

            try:
                stmt.version           = row['VERSAO']
                stmt.group             = row['GRUPO_DFP']
                stmt.cnpj              = row['CNPJ_CIA']
                stmt.corporate_name    = row['DENOM_CIA']
                stmt.currency_name     = row['MOEDA']
                stmt.currency_size     = row['ESCALA_MOEDA']
                stmt.fiscal_year_start = row['DT_INI_EXERC'] if 'DT_INI_EXERC' in row else ''
                stmt.fiscal_year_order = row['ORDEM_EXERC']
            except KeyError as e:
                logging.warn('failed to read row %d: %s', row_index, e)
                continue

            stmt.cvm_code        = cvm_code
            stmt.reference_date  = reference_date
            stmt.fiscal_year_end = fiscal_year_end
            stmt.accounts        = []

            stmts[stmt_key] = stmt
                
        stmt.accounts.append((row['CD_CONTA'], row['DS_CONTA'], row['VL_CONTA'], row['ST_CONTA_FIXA']))

    return stmts.values()

def reader(csv_file, delimiter: str = ';') -> Generator[Statement, None, None]:
    """Returns a generator that reads a DFP stmt from a CSV file."""

    for raw_stmt in _read_raw_statements(csv_file, delimiter):
        try:
            r = Statement()
            r.version                = int(raw_stmt.version)
            r.group, r.consolidated  = _read_statement_group(raw_stmt.group)
            r.company                = Company()
            r.company.cnpj           = raw_stmt.cnpj
            r.company.corporate_name = raw_stmt.corporate_name
            r.company.cvm_code       = raw_stmt.cvm_code
            r.currency               = normalize_currency(raw_stmt.currency_name)
            r.reference_date         = date_from_string(raw_stmt.reference_date)
            r.fiscal_year_start      = date_from_string(raw_stmt.fiscal_year_start) if raw_stmt.fiscal_year_start != '' else None
            r.fiscal_year_end        = date_from_string(raw_stmt.fiscal_year_end)
            r.fiscal_year_order      = FiscalYearOrder(raw_stmt.fiscal_year_order)
            r.accounts               = []

            for code, name, quantity, is_fixed in raw_stmt.accounts:
                acc = Account()
                acc.code     = code
                acc.name     = name
                acc.quantity = normalize_quantity(float(quantity), raw_stmt.currency_size)
                acc.is_fixed = is_fixed == 'S'

                r.accounts.append(acc)
        except ValueError as exc:
            logging.warn(
                'failed to parse stmt of company %s (CVM: %s, fiscal year end: %s): %s',
                raw_stmt.corporate_name,
                raw_stmt.cvm_code,
                raw_stmt.fiscal_year_end,
                exc
            )

        yield r