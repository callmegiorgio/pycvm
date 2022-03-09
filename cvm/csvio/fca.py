import contextlib
import io
import os
import typing
import zipfile
from cvm.csvio.document                       import RegularDocumentHeadReader, RegularDocumentBodyReader, UnexpectedBatch
from cvm.csvio.row                            import CSVRow
from cvm.datatypes.address                    import Address
from cvm.datatypes.auditor                    import Auditor
from cvm.datatypes.bookkeeping_agent          import BookkeepingAgent
from cvm.datatypes.contact                    import Contact
from cvm.datatypes.controlling_interest       import ControllingInterest
from cvm.datatypes.country                    import Country
from cvm.datatypes.industry                   import Industry
from cvm.datatypes.investor_relations_officer import InvestorRelationsOfficer, InvestorRelationsOfficerType
from cvm.datatypes.issuer                     import IssuerCompany, IssuerStatus
from cvm.datatypes.tax_id                     import CNPJ, CPF, InvalidTaxID
from cvm.datatypes.registration               import RegistrationCategory, RegistrationStatus
from cvm.datatypes.security                   import Security, SecurityType, MarketSegment, MarketType, PreferredShareType
from cvm.datatypes.shareholder_department     import ShareholderDepartmentPerson
from cvm.datatypes.trading_admission          import TradingAdmission
from cvm.doctypes.fca                         import FCA
from cvm.utils                                import date_from_string

class _MemberNameList:
    head_filename: str
    auditor_filename: str
    dissemination_channel_filename: str
    shareholder_department_filename: str
    investor_relations_department_filename: str
    address_filename: str
    bookkeeper_filename: str
    general_filename: str
    foreign_country_filename: str
    securities_filename: str

    def __init__(self, namelist: typing.Iterable[str]):
        self.head_filename                          = ''
        self.auditor_filename                       = ''
        self.dissemination_channel_filename         = ''
        self.shareholder_department_filename        = ''
        self.investor_relations_department_filename = ''
        self.address_filename                       = ''
        self.bookkeeper_filename                    = ''
        self.general_filename                       = ''
        self.foreign_country_filename               = ''
        self.securities_filename                    = ''

        suffix_length = len('_YYYY.csv')

        for name in namelist:
            try:
                left_name = name[:-suffix_length]
            except IndexError:
                raise zipfile.BadZipFile(f"unexpected name for member file '{name}'")

            if   left_name == 'fca_cia_aberta':                             self.head_filename                          = name
            elif left_name == 'fca_cia_aberta_auditor':                     self.auditor_filename                       = name
            elif left_name == 'fca_cia_aberta_canal_divulgacao':            self.dissemination_channel_filename         = name
            elif left_name == 'fca_cia_aberta_departamento_acionistas':     self.shareholder_department_filename        = name
            elif left_name == 'fca_cia_aberta_dri':                         self.investor_relations_department_filename = name
            elif left_name == 'fca_cia_aberta_endereco':                    self.address_filename                       = name
            elif left_name == 'fca_cia_aberta_escriturador':                self.bookkeeper_filename                    = name
            elif left_name == 'fca_cia_aberta_geral':                       self.general_filename                       = name
            elif left_name == 'fca_cia_aberta_pais_estrangeiro_negociacao': self.foreign_country_filename               = name
            elif left_name == 'fca_cia_aberta_valor_mobiliario':            self.securities_filename                    = name
            else:
                raise zipfile.BadZipFile(f"unknown member file '{name}'")

class AddressReader(RegularDocumentBodyReader):
    """'fca_cia_aberta_endereco_YYYY.csv'"""

    def batch_id(self, row: CSVRow) -> int:
        return row.required('ID_Documento', int)

    def read(self, document_id: int) -> typing.List[Address]:
        addresses = []

        for row in self.read_expected_batch(document_id):
            # Tipo_Endereco						Pais	CEP		DDI_Telefone	DDD_Telefone	Telefone	DDI_Fax	DDD_Fax	Fax	Email

            addresses.append(Address(
                street      = row.required('Logradouro',   str),
                complement  = row.required('Complemento',  str),
                district    = row.required('Bairro',       str),
                city        = row.required('Cidade',       str),
                state       = row.required('Sigla_UF',     str),
                country     = row.required('Pais',         Country),
                postal_code = row.required('CEP',          int)
            ))

        return addresses

class TradingAdmissionReader(RegularDocumentBodyReader):
    """'fca_cia_aberta_pais_estrangeiro_negociacao_YYYY.csv'"""

    def batch_id(self, row: CSVRow):
        return row.required('ID_Documento', int)

    def read(self, document_id: int) -> typing.List[TradingAdmission]:
        batch = self.read_expected_batch(document_id)

        trading_admissions = []

        for row in batch:
            trading_admissions.append(TradingAdmission(
                foreign_country = row.required('Pais',                     Country),
                admission_date  = row.required('Data_Admissao_Negociacao', date_from_string)
            ))

        return trading_admissions

class IssuerCompanyReader(RegularDocumentBodyReader):
    """'fca_cia_aberta_geral_YYYY.csv'"""

    def batch_id(self, row: CSVRow):
        return row.required('ID_Documento', int)

    def read(self,
             document_id: int,
             trading_admissions: typing.Sequence[TradingAdmission],
             addresses: typing.Sequence[Address]
    ) -> IssuerCompany:
        batch = self.read_expected_batch(document_id)
        row   = batch.rows[0]

        return IssuerCompany(
            corporate_name                    = row.required('Nome_Empresarial',                  str),
            corporate_name_last_changed       = row.optional('Data_Nome_Empresarial',             date_from_string),
            previous_corporate_name           = row.required('Nome_Empresarial_Anterior',         str),
            establishment_date                = row.required('Data_Constituicao',                 date_from_string),
            cnpj                              = row.required('CNPJ_Companhia',                    CNPJ),
            cvm_code                          = row.required('Codigo_CVM',                        int),
            cvm_registration_date             = row.required('Data_Registro_CVM',                 date_from_string),
            cvm_registration_category         = row.required('Categoria_Registro_CVM',            RegistrationCategory),
            cvm_registration_category_started = row.required('Data_Categoria_Registro_CVM',       date_from_string),
            cvm_registration_status           = row.required('Situacao_Registro_CVM',             RegistrationStatus),
            cvm_registration_status_started   = row.required('Data_Situacao_Registro_CVM',        date_from_string),
            home_country                      = row.required('Pais_Origem',                       Country),
            securities_custody_country        = row.required('Pais_Custodia_Valores_Mobiliarios', Country),
            trading_admissions                = tuple(iter(trading_admissions)),
            industry                          = row.required('Setor_Atividade',                   Industry),
            issuer_status                     = row.required('Situacao_Emissor',                  IssuerStatus),
            issuer_status_started             = row.required('Data_Situacao_Emissor',             date_from_string),
            controlling_interest              = row.required('Especie_Controle_Acionario',        ControllingInterest),
            controlling_interest_last_changed = row.optional('Data_Especie_Controle_Acionario',   date_from_string),
            fiscal_year_end_day               = row.required('Dia_Encerramento_Exercicio_Social', int),
            fiscal_year_end_month             = row.required('Mes_Encerramento_Exercicio_Social', int),
            fiscal_year_last_changed          = row.optional('Data_Alteracao_Exercicio_Social',   date_from_string),
            webpage                           = row.required('Pagina_Web',                        str),
            communication_channels            = (),
            addresses                         = tuple(iter(addresses)),
            contact                           = None # TODO
        )

class SecurityReader(RegularDocumentBodyReader):
    """'fca_cia_aberta_valor_mobiliario_YYYY.csv'"""

    def batch_id(self, row: CSVRow) -> int:
        return row.required('ID_Documento', int)

    def read_one(self, row: CSVRow) -> Security:
        return Security(
            type                          = row.required('Valor_Mobiliario',              SecurityType),
            market_type                   = row.required('Mercado',                       MarketType),
            market_managing_entity_symbol = row.required('Sigla_Entidade_Administradora', str),
            market_managing_entity_name   = row.required('Entidade_Administradora',       str),
            preferred_share_type          = row.optional('Classe_Acao_Preferencial',      PreferredShareType),
            bdr_unit_composition          = row.optional('Composicao_BDR_Unit',           str),
            trading_symbol                = row.required('Codigo_Negociacao',             str),
            trading_started               = row.optional('Data_Inicio_Negociacao',        date_from_string),
            trading_ended                 = row.optional('Data_Fim_Negociacao',           date_from_string),
            market_segment                = row.optional('Segmento',                      MarketSegment),
            listing_started               = row.optional('Data_Inicio_Listagem',          date_from_string),
            listing_ended                 = row.optional('Data_Fim_Listagem',             date_from_string)
        )

    def read(self, document_id: int) -> typing.List[Security]:
        batch      = self.read_expected_batch(document_id)
        securities = [self.read_one(row) for row in batch.rows]

        return securities

class AuditorReader(RegularDocumentBodyReader):
    """'fca_cia_aberta_auditor_YYYY.csv'"""

    def batch_id(self, row: CSVRow) -> int:
        return row.required('ID_Documento', int)

    def read_one(self, row: CSVRow) -> Auditor:
        tax_id_str = row.required('CPF_CNPJ_Auditor', str)

        try:
            tax_id = CNPJ(tax_id_str)
        except InvalidTaxID:
            try:
                tax_id = CPF(tax_id_str)
            except InvalidTaxID as exc:
                raise exc from None

        return Auditor(
            name                                = row.required('Auditor',                                 str),
            tax_id                              = tax_id,
            cvm_code                            = row.required('Codigo_CVM_Auditor',                      int),
            activity_started                    = row.required('Data_Inicio_Atuacao_Auditor',             date_from_string),
            activity_ended                      = row.optional('Data_Fim_Atuacao_Auditor',                date_from_string),
            technical_manager_name              = row.required('Responsavel_Tecnico',                     str),
            technical_manager_cpf               = row.required('CPF_Responsavel_Tecnico',                 CPF),
            technical_manager_activity_started  = row.required('Data_Inicio_Atuacao_Responsavel_Tecnico', date_from_string),
            technical_manager_activity_ended    = row.optional('Data_Fim_Atuacao_Responsavel_Tecnico',    date_from_string),
        )

    def read(self, document_id: int) -> typing.List[Auditor]:
        batch    = self.read_expected_batch(document_id)
        auditors = [self.read_one(row) for row in batch.rows]

        return auditors

class BookkeepingAgentReader(RegularDocumentBodyReader):
    """'fca_cia_aberta_escriturador_YYYY.csv'"""

    def batch_id(self, row: CSVRow) -> int:
        return row.required('ID_Documento', int)

    def read_one(self, row: CSVRow) -> BookkeepingAgent:
        address = Address(
            street      = row.required('Logradouro',  str),
            complement  = row.required('Complemento', str),
            district    = row.required('Bairro',      str),
            city        = row.required('Cidade',      str),
            state       = row.required('Sigla_UF',    str),
            country     = row.required('Pais',        Country),
            postal_code = row.required('CEP',         int)
        )

        contact = Contact(
            phone = None, # TODO
            fax   = None, # TODO
            email = row.optional('Email', str)
        )

        return BookkeepingAgent(
            name             = row.required('Escriturador',      str),
            cnpj             = row.required('CNPJ_Escriturador', CNPJ),
            address          = address,
            contact          = contact,
            activity_started = row.optional('Data_Inicio_Atuacao', date_from_string),
            activity_ended   = row.optional('Data_Fim_Atuacao',    date_from_string)
        )

    def read(self, document_id: int) -> typing.List[BookkeepingAgent]:
        batch              = self.read_expected_batch(document_id)
        bookkeeping_agents = [self.read_one(row) for row in batch.rows]

        return bookkeeping_agents

class InvestorRelationsDepartmentReader(RegularDocumentBodyReader):
    """'fca_cia_aberta_dri_YYYY.csv'"""

    def batch_id(self, row: CSVRow) -> int:
        return row.required('ID_Documento', int)

    def read_one(self, row: CSVRow) -> InvestorRelationsOfficer:
        address = Address(
            street      = row.required('Logradouro',  str),
            complement  = row.optional('Complemento', str),
            district    = row.required('Bairro',      str),
            city        = row.required('Cidade',      str),
            state       = row.required('Sigla_UF',    str), # TODO
            country     = row.required('Pais',        Country),
            postal_code = row.required('CEP',         int)
        )

        contact = Contact(
            phone = None, # TODO
            fax   = None, # TODO
            email = row.optional('Email', str)
        )

        return InvestorRelationsOfficer(
            type             = row.required('Tipo_Responsavel', InvestorRelationsOfficerType),
            name             = row.required('Responsavel',      str),
            cpf              = row.required('CPF_Responsavel',  CPF),
            address          = address,
            contact          = contact,
            activity_started = row.required('Data_Inicio_Atuacao', date_from_string),
            activity_ended   = row.optional('Data_Fim_Atuacao',    date_from_string)
        )

    def read(self, document_id: int) -> typing.List[InvestorRelationsOfficer]:
        batch = self.read_expected_batch(document_id)
        ird   = [self.read_one(row) for row in batch]

        return ird

class ShareholderDepartmentReader(RegularDocumentBodyReader):
    """'fca_cia_aberta_departamento_acionistas_YYYY.csv'"""

    def batch_id(self, row: CSVRow) -> int:
        return row.required('ID_Documento', int)

    def read_one(self, row: CSVRow) -> ShareholderDepartmentPerson:
        address = Address(
            street      = row.required('Logradouro',  str),
            complement  = row.optional('Complemento', str),
            district    = row.required('Bairro',      str),
            city        = row.required('Cidade',      str),
            state       = row.required('Sigla_UF',    str), # TODO
            country     = row.required('Pais',        Country),
            postal_code = row.required('CEP',         int)
        )

        contact = Contact(
            phone = None, # TODO
            fax   = None, # TODO
            email = row.optional('Email', str)
        )
        
        return ShareholderDepartmentPerson(
            name             = row.required('Contato', str),
            address          = address,
            contact          = contact,
            activity_started = row.optional('Data_Inicio_Contato', date_from_string),
            activity_ended   = row.optional('Data_Fim_Contato',    date_from_string)
        )
    
    def read(self, document_id: int) -> typing.List[ShareholderDepartmentPerson]:
        batch             = self.read_expected_batch(document_id)
        sharedholder_dept = [self.read_one(row) for row in batch]

        return sharedholder_dept

def reader(file: zipfile.ZipFile) -> typing.Generator[FCA, None, None]:
    namelist = _MemberNameList(iter(file.namelist()))

    with contextlib.ExitStack() as stack:
        def open_on_stack(filename: str):
            return stack.enter_context(io.TextIOWrapper(file.open(filename), encoding='ISO-8859-1'))

        head_reader              = RegularDocumentHeadReader        (open_on_stack(namelist.head_filename))
        address_reader           = AddressReader                    (open_on_stack(namelist.address_filename))
        trading_admission_reader = TradingAdmissionReader           (open_on_stack(namelist.foreign_country_filename))
        issuer_company_reader    = IssuerCompanyReader              (open_on_stack(namelist.general_filename))
        security_reader          = SecurityReader                   (open_on_stack(namelist.securities_filename))
        auditor_reader           = AuditorReader                    (open_on_stack(namelist.auditor_filename))
        bookkeeping_agent_reader = BookkeepingAgentReader           (open_on_stack(namelist.bookkeeper_filename))
        ird_reader               = InvestorRelationsDepartmentReader(open_on_stack(namelist.investor_relations_department_filename))
        shareholder_dept_reader  = ShareholderDepartmentReader      (open_on_stack(namelist.shareholder_department_filename))

        while True:
            head = head_reader.read()

            try:
                addresses = address_reader.read(head.id)
            except UnexpectedBatch:
                addresses = ()

            try:
                trading_admissions = trading_admission_reader.read(head.id)
            except UnexpectedBatch:
                trading_admissions = ()

            try:
                issuer_company = issuer_company_reader.read(head.id, trading_admissions, addresses)
            except UnexpectedBatch:
                issuer_company = None

            try:
                securities = security_reader.read(head.id)
            except UnexpectedBatch:
                securities = ()

            try:
                auditors = auditor_reader.read(head.id)
            except UnexpectedBatch:
                auditors = ()

            try:
                bookkeeping_agents = bookkeeping_agent_reader.read(head.id)
            except UnexpectedBatch:
                bookkeeping_agents = ()
            
            try:
                ird = ird_reader.read(head.id)
            except UnexpectedBatch:
                ird = ()

            try:
                shareholder_dept = shareholder_dept_reader.read(head.id)
            except UnexpectedBatch:
                shareholder_dept = ()

            yield FCA(
                cnpj                          = head.cnpj,
                reference_date                = head.reference_date,
                version                       = head.version,
                company_name                  = head.company_name,
                cvm_code                      = head.cvm_code,
                type                          = head.type,
                id                            = head.id,
                receipt_date                  = head.receipt_date,
                url                           = head.url,
                issuer_company                = issuer_company,
                securities                    = tuple(securities),
                auditors                      = tuple(auditors),
                bookkeeping_agents            = tuple(bookkeeping_agents),
                investor_relations_department = tuple(ird),
                shareholder_department        = tuple(shareholder_dept)
            )