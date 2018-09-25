from garden.db import get_db
import uuid

def scrub(table_name):
    return ''.join(chr for chr in table_name if (chr.isalnum() or chr == "_"))

class Model(object):
    def __init__(self, *initial_data, **kwargs):
        self._keys = {}
        
        for dictionary in initial_data:
            for key in dictionary:
                self.setAttribute(key, dictionary[key])
        for key in kwargs:
            self.setAttribute(key, kwargs[key])
        
        if not self.hasAttribute('uuid'):
            self.setAttribute("uuid", str(uuid.uuid4()))

        self._persisted = False
        self._clean = False

        self.afterInit()

    def afterInit(self):
        pass

    def fromDB(self):
        self._persisted = True
        self._clean = True

        return self

    """DB-based attributes"""
    def setAttribute(self, key, value):
        setattr(self, key, value)
        if key not in self._keys:
            self._keys[key] = True

    """DB-based attributes"""
    def hasAttribute(self, key):
        return hasattr(self, key) and (key in self._keys)

    """DB-based attributes"""
    def getAttribute(self, key):
        if self.hasAttribute(key):
            return getattr(self, key)
        else:
            return None

    def set(self, key, value):
        self.setAttribute(key, value)
        self._clean = False

    def refresh(self):
        if not self._persisted:
            return False

        row = get_db().execute(
                'SELECT * FROM ' + scrub(self._table) + ' WHERE uuid=:uuid', self.dictionary()
        ).fetchone()

        if not row:
            return False

        for key in row.keys():
            self.setAttribute(key, row[key])

        self._clean = True

    def preSave(self):
        pass

    def save(self):
        self.preSave()

        dictionary = self.dictionary()

        db = get_db()

        if self._persisted:
            params = []
            for key in dictionary:
                params.append(scrub(key) + '=:' + scrub(key))

            db.execute(
                'UPDATE ' + scrub(self._table) + ' SET ' + ', '.join(params) + ' WHERE uuid=:uuid', dictionary
            )
            db.commit()
        else:
            columns = []
            params = []
            for key in dictionary:
                columns.append(scrub(key))
                params.append(':' + scrub(key))

            db.execute(
                'INSERT INTO ' + scrub(self._table) + ' (' + ', '.join(columns) + ') VALUES (' + ', '.join(params) + ')', dictionary
            )
            db.commit()

        self._persisted = True
        self._clean = True
        return

    def dictionary(self):
        dictionary = {}

        for key in self._keys:
            dictionary[key] = getattr(self, key)
        return dictionary

    @classmethod
    def fromRow(cls, row):
        dictionary = {}
        for key in row.keys():
            dictionary[key] = row[key]
        return cls(dictionary).fromDB()

    @classmethod
    def recordsByUUID(cls):
        collection = Collection(cls)
        collection.recordsByUUID()
        return collection

class Collection(object):
    def __init__(self, model_class):
        self.model_class = model_class
        self.records = {}

    def filteredCollection(self, param, value):
        output = Collection(self.model_class)
        
        for model in self.iterate():
            if model.getAttribute(param) == value:
                output.pushExistingModel(model)

        return output

    def recordsByUUID(self):
        db = get_db()

        rows = db.execute(
            'SELECT * FROM ' + scrub(self.model_class._table)
        ).fetchall()

        for row in rows:
            self.records[row['uuid']] = self.model_class.fromRow(row=row)

    def fetchByUUID(self, uuid):
        if uuid in self.records:
            return self.records[uuid]
        return None

    def pushRows(self, rows):
        for row in rows:
            self.records[row['uuid']] = self.model_class.fromRow(row=row)

    def pushExistingModel(self, model):
        self.records[model.uuid] = model

    def addNewRecord(self, dictionary):
        record = self.model_class(dictionary)
        self.records[record.uuid] = record
        return record

    def iterate(self):
        for key in self.records:
            record = self.fetchByUUID(key)
            if record:
                yield self.fetchByUUID(key)

    def count(self):
        return len(self.records)
