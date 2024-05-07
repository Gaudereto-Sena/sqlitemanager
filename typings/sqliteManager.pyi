from __future__ import annotations
import os
import pandas as pd
import sqlite3
from collections.abc import Callable
from typing import List, Optional, Union, TypeVar, Type, Generic
from dataclasses import dataclass, field,  fields
from unidecode import unidecode
from enum import Enum
import re
"""
Decorator para propriedades de classe de forma tipada

URL: https://stackoverflow.com/questions/75062897/how-to-have-typing-support-for-a-static-property-using-a-decorator
"""
R = TypeVar("R")    
class classproperty(Generic[R]):
    def __init__(self, getter: Callable[[], R]) -> None:
        self.__getter = getter

    def __get__(self, obj: object, objtype: type) -> R:
        return self.__getter(objtype)

    @staticmethod
    def __call__(getter_fn: Callable[[], R]) -> classproperty[R]:
        return classproperty(getter_fn)

class ForeignKeyAction(Enum):
    CASCADE = "CASCADE"
    SET_NULL = "SET NULL"
    RESTRICT = "RESTRICT"
    NO_ACTION = "NO ACTION"
    
class ColumnTypes(Enum):
    VARCHAR = "VARCHAR"
    TEXT = "TEXT"
    INT = "INT"
    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"
    DATE = "DATE"
    DATETIME = "DATETIME"
   
@dataclass
class ForeignKey:
    key: str
    referenceModel: Model # can be the model or a string with its value
    referenceKey: str
    onDelete: ForeignKeyAction = ForeignKeyAction.RESTRICT
    onUpdate: ForeignKeyAction = ForeignKeyAction.NO_ACTION
    __model: 'Model' = None
    
    def __post_init__(self):
        self.__schema = None
        
    def createSchema(self): 
        self.getModel()  

        self.__schema = f"FOREIGN KEY ({self.key}) REFERENCES {self.referenceModel.modelTableName}({self.referenceKey}) ON DELETE {self.onDelete.value} ON UPDATE {self.onUpdate.value}"
        
        return self.schema

    @property
    def schema(self):
        if not self.__schema:
            self.__schema = self.createSchema()
        return self.__schema
    
    def getModel(self):
        if not self.__model:
            self.__model = globals()["Model"]
        
        if isinstance(self.referenceModel, str):
            self.referenceModel =  globals()[self.referenceModel]  
                       
        if not issubclass(self.referenceModel, self.__model):
            raise Exception("Atributo referenceModel deve ser uma instância de Model")
        
        return self.referenceModel
    
@dataclass
class ColumnOptions:
    type: ColumnTypes 
    precision: str | int = None
    default: str = None
    nullable: bool = True
    primaryKey: bool = False
    autoIncrement: bool = False
    definitions: List[str] = None

@dataclass
class Column:
    name: str
    options: ColumnOptions
 
class Model():
    __tableName: str
    __columns: List[Column]
    __foreignKeys: List[ForeignKey] = []
    __foreignKeysModels = []
    
    def __init__(self, tableName, columns: List[Column], foreingKeys: List[ForeignKey] = None):
        self.__tableName = tableName
        self.__columns = columns
        self.__foreignKeys = foreingKeys
        self.__schema = self.__createSchema()  
    
    def __iter__(self):
        return self.columns
    
    def __createSchema(self):
        tableName = self.tableName
        
        columns = []
        hasPrimaryKey = False
        for column in self.__columns:
            if column.name:
                columnName = unidecode(column.name.lower().strip().replace(' ', '_'))
            else: continue
            
            # if column.options.type in self.__allowedTypes:
            fieldType = column.options.type.value 
            # else: continue
            
            if column.options.primaryKey:
                primaryKey = "PRIMARY KEY "
                hasPrimaryKey = True
            else:
                primaryKey = ""
            
            autoIncrement = "AUTOINCREMENT " if column.options.autoIncrement else ""
            precision = f"({column.options.precision}) " if column.options.precision else ""
            nullable = "NOT NULL " if not column.options.nullable else ""
            default = f"DEFAULT {column.options.default} " if column.options.default else ""
            definitions = f"{column.options.definitions} " if column.options.definitions else ""

            columnSchema = f"{columnName} {fieldType}{precision} {primaryKey}{autoIncrement}{nullable}{default}{definitions} "
            
            columns.append(columnSchema)
            
        if not hasPrimaryKey:
            raise Exception(f"Invalid Model: {tableName} doesn't have a primary key.")
        
       
        if len(self.__foreignKeys):
            foreingKeys = [fk.schema for fk in self.__foreignKeys]   
            columns.extend(foreingKeys)
        
        sql = f"CREATE TABLE IF NOT EXISTS {tableName} ({', '.join(x.strip() for x in columns)});"
        return sql
    
    @staticmethod
    def addForeignKeys(foreignKeys: List[ForeignKey]):
        Model.__foreignKeys.extend(foreignKeys)
    
    @classproperty
    def modelTableName(cls) -> str:
        return getattr(cls, f"_{cls.__name__}__tableName", None)
    
    @classproperty
    def modelForeignKeys(cls) -> List[ForeignKey]:
        foreignKeys : List[ForeignKey] = getattr(cls, f"_{cls.__name__}__foreignKeys", List[ForeignKey])
        return foreignKeys
    
    @classproperty
    def modelColumns(cls) -> List[str]:
        columns: List[Column] = getattr(cls, f"_{cls.__name__}__columns", None)
        columnsNames = [column.name for column in columns]
        return columnsNames
    
    @property
    def tableName(self) -> str:
        return self.__tableName
    
    @property
    def foreignKeys(self) -> List[ForeignKey]:
        return self.__foreignKeys
     
    @property
    def columns(self) -> List[str]:
        columnsNames = [column.name for column in self.__columns]
        return columnsNames
    
    @property
    def schema(self):
        return self.__schema

class JoinTypes(Enum):
    LEFT = "LEFT JOIN" 
    INNER = "INNER JOIN"
    RIGHT = "RIGHT JOIN"
    FULL = "FULL JOIN"
    CROSS = "CROSS JOIN"

@dataclass
class JoinOptions:
    table: str
    alias: str
    type: JoinTypes = JoinTypes.INNER
    
    def __eq__(self, other):
        return self.table == other
    
@dataclass
class QueryOptions:
    fields: List[str] =  field(default_factory=list)
    where: List[str] =  field(default_factory=list)
    orderBy: List[str] =  field(default_factory=list)
    limit: List[str] =  field(default_factory=list)
    offset: List[str] =  field(default_factory=list)
    join: List[JoinOptions] =  field(default_factory=list)
    tableModel: Model = None
    __model: Model = Model
    
    def __post_init__(self):
        if self.tableModel is None:
            return  
        # Inicializando o model e atribui a referência da classe ao objeto
        self.__getModel()
        # Busca os fields presentes no model
        self.__fieldsModel = self.__setFieldsOfModel([self.tableModel])
        self.__alias = None
        self.__joinSchema = None
        # Busca as foreingKeys se join estiver definido
        if len(self.join) > 0:
            if not self.tableModel.modelTableName in self.join:
                # Deve ser substituido por um alias padrão
                raise Exception("Tabela principal da busca não possui definição de alias no Join")
            
            self.__alias = next((joinOption.alias for joinOption in self.join if joinOption.table == self.tableModel.modelTableName), None)
            self.__modelsFk = [fk.getModel() for fk in self.tableModel.modelForeignKeys]
            # Pega os fields dos models das FK e atribui a eles o alias correspondente no Join e adiciona aos fields do Model
            self.__fieldsFk = self.__setFieldsOfModel(self.__modelsFk)
            self.__fieldsModel.extend(self.__fieldsFk)
            self.__joinSchema = self.__createJoinsSchema()
        
        if not set(self.fields).issubset(self.__fieldsModel):
            raise Exception("Campos buscados não correspondem aos campos presentes nas tabelas")     
        
        self.schema = self.__createSchema()

    def __setFieldsOfModel(self, models: List[Model]):
        # Adiciona o alias aos campos de cada model
        if len(self.join) > 0:
            fields = [f"{joinOption.alias}.{key}" for model in models for joinOption in list(filter(lambda x: x.table == model.modelTableName, self.join)) for key in model.modelColumns]
        else:
            # Mantem os campos sem aliases caso não haja joins definidos
            fields = [f"{key}" for model in models for key in model.modelColumns]
         
        return fields

    def __createJoinsSchema(self):
        if not set(self.fields).issubset(set(self.__fieldsModel)):
            raise Exception("Campos informados não estão presentes no model e em seus constrains")

        joinSchema = []
        # Busca o alias correspondente ao modulo atual
        
        for joinOption in self.join:
            modelFk = next((modelFk for modelFk in self.tableModel.modelForeignKeys if joinOption.table == modelFk.referenceModel.modelTableName), None)
            
            if not modelFk:
                continue
            
            joinSchema.append(f"{joinOption.type.value} {joinOption.table} as {joinOption.alias} ON {joinOption.alias}.{modelFk.referenceKey} = {self.__alias}.{modelFk.key}") 
        
        return joinSchema  
            
    def __createSchema(self):
        table = self.tableModel.modelTableName
        tableAlias = f" as {self.__alias}" if self.__alias else ""
        join = " ".join([""]+self.__joinSchema) if self.__joinSchema else ""
        fields = ", ".join(self.fields) if self.fields else  ' * '
        where = " WHERE " + ' AND '.join(self.where) if self.where else ""
        orderBy = " ORDER BY " + ', '.join(self.orderBy) if self.orderBy else ""
        limit = f" LIMIT {self.limit}" if self.limit else ""
        offset = f" OFFSET {self.offset}" if self.offset else ""
    
        sql = f"SELECT {fields} FROM {table}{tableAlias}{join}{where}{orderBy}{limit}{offset};"
        return sql
        
    def __getModel(self):
        if not self.__model:
            self.__model = globals()["Model"]
                    
        if isinstance(self.tableModel, str):
            self.tableModel = globals()[self.tableModel] 
        
        if not issubclass(self.tableModel, self.__model):    
            raise Exception("Atributo referenceModel deve ser uma instância de Model")
        
        return self.tableModel
     
M = TypeVar('M', bound=Model)             
class QueryBuilder(Generic[M]):
    
    def __init__(self, connection: sqlite3.Connection, model: Type[M]):
        self.__connection = connection
        self.__cursor = self.__connection.cursor()
        self.__model =  model
        self.__tableName = model.modelTableName
        self.__foreignKeys = model.modelForeignKeys
        self.__foreignKeysModels = [fk.getModel() for fk in self.__foreignKeys]
        
    def findOne(self, queryOptions : QueryOptions = None):
        
        if queryOptions is None:
            queryOptions = QueryOptions(self.__model)
        elif queryOptions.tableModel is None:
            queryOptions_dict = queryOptions.__dict__
            queryOptions_dict.pop('tableModel', None)
            queryOptions = QueryOptions(tableModel=self.__model, **queryOptions_dict)
        
        sql = "SELECT 1 from cargos"
        try:
            self.__cursor.execute(sql)
            self.commitChanges()
            return self
        except sqlite3.Error as e:
            print('Erro ao executar a query', e)
            
    def executeSQL(self, sql, commitChanges : bool = True):
        try:
            self.__cursor.execute(sql)
            self.commitChanges() if commitChanges else None
            return self
        except sqlite3.Error as e:
            print('Erro ao executar a query', e)

    def executeMany(self, sql, params, commitChanges : bool = True):
        try:
            self.__cursor.executemany(sql, params)
            self.commitChanges() if commitChanges else None
        except sqlite3.Error as e:
            print('Erro ao executar as queries', e)
    
    # { "type": str, "onClause":str, table: str}
    def selectTable(self, table: str, options : dict = { "fields": [], "where": [], "orderBy": [], "limit": None, "offset": None , "join": []}, printData : bool = False):
        
        if 'fields' in options and len(options['fields']) > 0: fields = ', '.join(options["fields"])
        else: fields = ' * '
        if 'where' in options and len(options['where']) > 0: where = " WHERE " + ' AND '.join(options["where"])
        else: where = ''
        if 'orderBy' in options and len(options['orderBy']) > 0: orderBy = " ORDER BY " + ', '.join(options["orderBy"])
        else: orderBy = ''
        if 'limit' in options and isinstance(options['limit'], int) and options['limit'] > 0 : limit = f" LIMIT {options['limit']}"
        else: limit = ''
        if 'offset' in options and isinstance(options['offset'], int) and options['offset'] > 0: offset = f" OFFSET {options['offset']}"
        else: offset = ''
        if 'join' in options and len(options['join']) > 0: join = " ".join([f" {joinData['type']} {joinData['table']} ON {joinData['onClause']}" for joinData in options['join']])
        else: join = ''
        
        sql = f"SELECT {fields} FROM {table}{join}{where}{orderBy}{limit}{offset} ;"
        print(sql)
        
        self.executeSQL(sql)
        if printData: self.printData()
        
        return self
    
    def printData(self):
        data = self.__cursor.fetchall()
        
        for line in data:
            print(line)    
        
    def closeConection(self):
        self.__connection.close()
        
    def commitChanges(self):
        self.__connection.commit()

class SqliteManager:
    
    def __init__(self, models: List[Type[Model]], pathDb: str = None, createOnDB: bool = False):
        self.__models = models
        self.__tableNames = []
        if pathDb:
            self.initializeModelsGlobaly(self.__models)
            self.pathDb = pathDb
            self.__connection = sqlite3.connect(self.pathDb)
            
            for model in models:
                modelName = model.__name__[:1].lower() + model.__name__[1:]
                setattr(self, modelName, QueryBuilder[model](self.__connection, model))
                self.__tableNames.append(model.modelTableName)
            
            self.__createSchema = self.initDB(self.__models)
            if createOnDB:
                self.executeSql(self.__createSchema)
               
    def __dir__(self):
        default_attrs = dir(type(self))
        dynamic_attrs = [attr for attr in vars(self) if not attr.startswith("__")]
        return sorted(default_attrs + dynamic_attrs)
    
    @classproperty
    def baseInterface(cls):
        """ Ao adicionar uma nova funcionalidade, deve-se adicionar a sua correspondente na variavel interface """
        interface = """
class SqliteManager:
\tpathDb: str
\tdef initDB(self) -> None: ...
\t@staticmethod
\tdef generateMigration() -> None: ...
\t@property
\tdef tableNames(self) -> list[str]: ...
\tdef executeSql(self, sql: Union[str, list[str]]): ... 
"""
        return interface
    
    @staticmethod
    def initDB(models: List[Model], initFilename = 'init') -> str:
        initSchema = [model().schema for model in models]
        
        dirname = os.path.dirname(__file__)
        migrationPath = os.path.join(dirname, 'migration/')
        try:
            if not os.path.exists(migrationPath):
                os.mkdir(migrationPath)
                
            filepath = os.path.join(migrationPath, f"{initFilename}.sql")
            f = open(filepath, "w")
            f.write("\n\n".join(initSchema))
            return initSchema
        except:
            raise Exception("Falha ao gerar init.sql")  
        
    @staticmethod
    def generateMigration(pathDB: str = None, initFilename = 'init'):
        models = Model.__subclasses__()
        modelsDefinitions = InterfaceWriter.extractModels('./models.py')
        modelsImplementations = "#" * 34
        modelsImplementations += "\n# CLASSES IMPORTADAS DO MODEL #\n"
        modelsImplementations += "#" * 34 + "\n"
        modelsImplementations += InterfaceWriter.generateInterface(modelsDefinitions)
        modelsImplementations += InterfaceWriter.readModelFile('./models.py')
        InterfaceWriter.overwriteInterfaceFromLine('./typings/SqliteManager.pyi', 400, modelsImplementations)
        # print(modelsImplementations)
        if models:
            for model in models:
                globals()[model.__name__] = model
                
            schema = SqliteManager.initDB(models, initFilename)
            if pathDB:
                SqliteManager.__executeSql(schema, pathDB)
        else:
            raise Exception("Não foram encontrados Models para gerar schema.")
    
    @staticmethod   
    def checkDb(pathDb):
        connection = sqlite3.connect(pathDb)
        cursor = connection.cursor()
        
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(tables)
        # for table_name, create_statement in tables:
        #     print("Table:", table_name)
        #     print("Schema:")
        #     print(create_statement)
    
    def executeSql(self, sql: Union[str, list[str]]):
        try:
            cursor = self.__connection.cursor()
            if isinstance(sql, list): 
                [cursor.execute(sqlStatement) for sqlStatement in sql]
            else: 
                cursor.execute(sql)
            self.__connection.commit()
            return self
        except sqlite3.Error as e:
            print('Erro ao executar a query', e)
            
    @staticmethod        
    def __executeSql(cls, sql: Union[str, list[str]], pathDB):
        try:
            with sqlite3.connect(pathDB) as connection:
                cursor = connection.cursor()
                if isinstance(sql, list): 
                    [cursor.execute(sqlStatement) for sqlStatement in sql]
                else: 
                    cursor.execute(sql)
                connection.commit()
                connection.close()
        except sqlite3.Error as e:
            print('Erro ao executar a query', e)
            
    @staticmethod
    def initializeModelsGlobaly(models):
        if models:
            for model in Model.__subclasses__():
                globals()[model.__name__] = model 
    
    @property
    def tableNames(self) -> list[str]:
        return self.__tableNames
    
class InterfaceWriter:
    
    @staticmethod
    def readModelFile(filePath):
        with open(filePath, 'r') as file:
            code = file.read()
            code = re.sub(r'^(import|from).+?(?=\\n|$)', '', code, flags=re.MULTILINE).strip()
        return code
    
    @staticmethod
    def extractModels(input_file):
        with open(input_file, 'r') as f:
            content = f.read()
        # Acha todas as definições de classe
        class_defs = re.findall(r'class\s+([^\s\(]+)\s*\((?:[^)]*)(Model)(?:[^)]*)\)\s*:', content)
        
        return [definition[0] for definition in class_defs]
    
    @staticmethod
    def generateInterface(models: list[str]):
        baseInterface = SqliteManager.baseInterface
        modelsInterface = [f"{model[:1].lower()}{model[1:]} : {QueryBuilder.__name__}[{model}]" for model in models]
        finalInterface = baseInterface + "\t" + "\n\t".join(modelsInterface) + "\n\n"
        return finalInterface
           
    @staticmethod
    def overwriteInterfaceFromLine(filePath: str, linePosition, newInterface):
        with open(filePath, 'r+') as file:
            lines = file.readlines()
            if linePosition < 1 or linePosition > len(lines):
                print("Linha especificada está fora do intervalo.")
                return
            file.seek(0)
            for positon, line in enumerate(lines, 1):
                if positon < linePosition: file.write(line)
                else: file.truncate()
            
            file.write(newInterface)
             
    @staticmethod
    def writeClass(output_file, class_defs):
        """ Estudar qual o minimo de definição necessária para a classe dentro da interface """
        with open(output_file, 'w') as f:
            for class_name in class_defs:
                f.write(f"class {class_name}:\n")
                f.write("    pass\n\n")
 
##################################
# CLASSES IMPORTADAS DO MODEL #
##################################

class SqliteManager:
	pathDb: str
	def initDB(self) -> None: ...
	@staticmethod
	def generateMigration() -> None: ...
	@property
	def tableNames(self) -> list[str]: ...
	def executeSql(self, sql: Union[str, list[str]]) -> SqliteManager: ... 
	def printData(self) -> SqliteManager: ... 
	departamentos : QueryBuilder[Departamentos]
	funcionarios : QueryBuilder[Funcionarios]
	cargos : QueryBuilder[Cargos]
	dependentes : QueryBuilder[Dependentes]
	historicoSalarios : QueryBuilder[HistoricoSalarios]
	historicoSalariosNovo : QueryBuilder[HistoricoSalariosNovo]

class Departamentos(Model):
    __tableName = "departamentos"
    __columns = [
        Column(name="id", options=ColumnOptions(type=ColumnTypes.INTEGER, autoIncrement=True, primaryKey=True)),
        Column(name="nome_departamento", options=ColumnOptions(type=ColumnTypes.VARCHAR, precision=200, nullable=False)),
        Column(name="gerente_id", options=ColumnOptions(type=ColumnTypes.INT, precision=11)),
        Column(name="andar_departamento", options=ColumnOptions(type=ColumnTypes.INT, precision=7, nullable=False)),
        Column(name="orcamento", options=ColumnOptions(type=ColumnTypes.DECIMAL, precision="15,2"))
        ]
    __foreignKeys = [
        ForeignKey(key="gerente_id", referenceKey="id", referenceModel="Funcionarios", onDelete=ForeignKeyAction.SET_NULL, onUpdate=ForeignKeyAction.CASCADE)
        ]
    
    def __init__(self):
        Model.__init__(self, self.__tableName, self.__columns, self.__foreignKeys)
      
class Funcionarios(Model):
    __tableName = "funcionarios"
    __columns = [
        Column(name="id", options=ColumnOptions(type=ColumnTypes.INTEGER, autoIncrement=True, primaryKey=True)),
        Column(name="nome", options=ColumnOptions(type=ColumnTypes.VARCHAR, precision=150, nullable=False)),
        Column(name="cargo_id", options=ColumnOptions(type=ColumnTypes.INT, precision=11)),
        Column(name="departamento_id", options=ColumnOptions(type=ColumnTypes.INT, precision=11)),
        Column(name="salario_real", options=ColumnOptions(type=ColumnTypes.DECIMAL, precision="15,2", nullable=False)),
        Column(name="data_nova", options=ColumnOptions(nullable=False, default="CURRENT_DATE", type=ColumnTypes.DATETIME)),
        Column(name="genero", options=ColumnOptions(type=ColumnTypes.VARCHAR, precision=15, nullable=False, definitions="CHECK(genero IN ('Masculino', 'Feminino', 'Não definido'))")),
        Column(name="data_cadastro", options=ColumnOptions(type=ColumnTypes.DATE, nullable=False, default="CURRENT_DATE"))
        ]
    __foreignKeys = [
        ForeignKey(key="departamento_id", referenceKey="id", referenceModel=Departamentos, onDelete=ForeignKeyAction.SET_NULL, onUpdate=ForeignKeyAction.CASCADE),
        ForeignKey(key="cargo_id", referenceKey="id", referenceModel="Cargos", onDelete=ForeignKeyAction.SET_NULL, onUpdate=ForeignKeyAction.CASCADE)
    ]
    
    def __init__(self):
        Model.__init__(self, self.__tableName, self.__columns, self.__foreignKeys)
        
class Cargos(Model):
    __tableName = "cargos"
    __columns = [
        Column(name="id", options=ColumnOptions(type=ColumnTypes.INTEGER, autoIncrement=True, primaryKey=True)),
        Column(name="descricao", options=ColumnOptions(type=ColumnTypes.TEXT, nullable=False)),
        Column(name="salario_base", options=ColumnOptions(type=ColumnTypes.DECIMAL, precision="15,2", nullable=False)),
        Column(name="nivel_cargo", options=ColumnOptions(type=ColumnTypes.VARCHAR, precision=15, nullable=False, definitions="CHECK(nivel_cargo IN ('estagiário', 'técnico', 'analista', 'gerente', 'diretor'))")),
        Column(name="beneficios", options=ColumnOptions(type=ColumnTypes.TEXT, nullable=False))
    ]
    __foreignKeys = []
    
    def __init__(self):
        Model.__init__(self, self.__tableName, self.__columns, self.__foreignKeys)
        
class Dependentes(Model):
    __tableName = "dependentes"
    __columns = [
        Column(name="id", options=ColumnOptions(type=ColumnTypes.INTEGER, autoIncrement=True, primaryKey=True)),
        Column(name="funcionario_id", options=ColumnOptions(type=ColumnTypes.INT, precision=11, nullable=False)),
        Column(name="dependente", options=ColumnOptions(type=ColumnTypes.VARCHAR, precision=15, nullable=False, definitions="CHECK(dependente IN ('filha', 'filho', 'mãe', 'pai', 'avô', 'avó', 'neto', 'neta', 'irmão', 'irmã'))")),
        Column(name="idade", options=ColumnOptions(type=ColumnTypes.INT, precision="11"))
    ]
    __foreignKeys = [
        ForeignKey(key="funcionario_id", referenceKey="id", referenceModel=Funcionarios, onDelete=ForeignKeyAction.CASCADE, onUpdate=ForeignKeyAction.CASCADE)
    ]
    
    def __init__(self):
        Model.__init__(self, self.__tableName, self.__columns, self.__foreignKeys)
        
class HistoricoSalarios(Model):
    __tableName = "historico_salarios"
    __columns = [
        Column(name="id", options=ColumnOptions(type=ColumnTypes.INTEGER, autoIncrement=True, primaryKey=True)),
        Column(name="funcionario_id", options=ColumnOptions(type=ColumnTypes.INT, precision=11, nullable=False)),
        Column(name="data_pagamento", options=ColumnOptions(type=ColumnTypes.DATE, nullable=False)),
        Column(name="salario_recebido", options=ColumnOptions(type=ColumnTypes.DECIMAL, precision="15,2", nullable=False))
    ]
    __foreignKeys = [
        ForeignKey(key="funcionario_id", referenceKey="id", referenceModel=Funcionarios, onDelete=ForeignKeyAction.RESTRICT, onUpdate=ForeignKeyAction.CASCADE)
    ]
    
    def __init__(self):
        Model.__init__(self, self.__tableName, self.__columns, self.__foreignKeys)
        
class HistoricoSalariosNovo(Model):
    __tableName = "historico_salarios_novo"
    __columns = [
        Column(name="id", options=ColumnOptions(type=ColumnTypes.INTEGER, autoIncrement=True, primaryKey=True)),
        Column(name="funcionario_id", options=ColumnOptions(type=ColumnTypes.INT, precision=11, nullable=False)),
        Column(name="data_pagamento", options=ColumnOptions(type=ColumnTypes.DATE, nullable=False)),
        Column(name="salario_recebido", options=ColumnOptions(type=ColumnTypes.DECIMAL, precision="15,2", nullable=False))
    ]
    __foreignKeys = [
        ForeignKey(key="funcionario_id", referenceKey="id", referenceModel=Funcionarios, onDelete=ForeignKeyAction.RESTRICT, onUpdate=ForeignKeyAction.CASCADE)
    ]
    
    def __init__(self):
        Model.__init__(self, self.__tableName, self.__columns, self.__foreignKeys)