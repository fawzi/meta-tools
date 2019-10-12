from typing import Union, List, Optional, Dict
from enum import Enum
from pydantic import BaseModel, ValidationError, validator
from datetime import date
import hashlib, logging
import json, tempfile
import re, io
import os, os.path
jd = lambda x: json.dumps(x, sort_keys=True, ensure_ascii=True)
from collections import namedtuple

EntryDict = namedtuple('EntryDict', ['meta_info_entry', 'metadict_name'])


def replacePath(tmpPath, targetPath):
	"""If tmpPath is different from targetPath, replaces targetPath with the
 file at tmpPath, while keeping a backup .bk-<timestamp> at targetpath"""
	if not os.path.exists(targetPath):
		os.replace(tmpPath, targetPath)
		return
	m = hashlib.sha512()
	with open(tmpPath, 'rb') as f:
		while True:
			d = f.read(1024)
			if not d:
				break
			m.update(d)
	d1 = m.digest()
	m = hashlib.sha512()
	with open(targetPath, 'rb') as f:
		while True:
			d = f.read(1024)
			if not d:
				break
			m.update(d)
	d2 = m.digest()
	if d1 == d2:
		os.remove(tmpPath)
	else:
		timestamp = date.today().isoformat()
		t2 = targetPath + '.' + timestamp + '.bk'
		t3 = t2
		ii = 0
		while os.path.exists(t3):
			ii += 1
			t3 = f"{targetPath}.{timestamp}-{ii}.bk"
		os.replace(targetPath, t3)
		os.replace(tmpPath, targetPath)
		logging.info(f'changes in {targetPath}, old version in {t3}')


def writeFile(targetPath, writer):
	"""writes to target path keeping a backup of the old version"""
	name = os.path.basename(targetPath).split('.')[0][:10]
	dir = os.path.dirname(targetPath)
	if not dir:
		dir = '.'
	with tempfile.NamedTemporaryFile(
			mode='w', encoding='utf8', suffix=".tmp", prefix=name, dir=dir,
			delete=False) as fOut:
		try:
			writer(fOut)
			fOut.flush()
		except:
			raise Exception(
				f"Failure trying to write {targetPath}, leaving failed attempt in {fOut.name}"
			)
		replacePath(fOut.name, targetPath)


def safeRemove(toRm):
	"""moves the give files to a backup (unless they already are a backup (.bk))"""
	for f in toRm:
		if not f.endswith('.bk'):
			t2 = os.path.join(dir, f + '.' + timestamp + '.bk')
			t3 = t2
			ii = 0
			while os.path.exists(t3):
				ii += 1
				t3 = os.path.join(dir, f'{f}.{timestamp}-{ii}.bk')
			logging.warn('removing old meta_info_entry {f} (backup {t3})')
			os.replace(os.path.join(dir, f), t3)


def splitStr(string, maxLen=115):
	"""If the string has newlines or is longer than maxLen ({maxLen}) characters splits it.
	if maxLen is -1 it does not split. It always returns an array of strings""".format(
		maxLen=maxLen)
	toDo = string.splitlines(keepends=True)[::-1]
	if len(toDo) == 1 and len(string) < maxLen or maxLen == -1:
		return [string]
	res = []
	breakRe = re.compile(r"[\s\[\]\(\)\{\}.,<>;:!|\\/=+\-*&^%$#@?~]")
	while toDo:
		lNow = toDo.pop()
		if len(lNow) <= maxLen:
			res.append(lNow)
		else:
			rNow = lNow[maxLen - 1::-1]
			done = False
			for m in breakRe.finditer(rNow):
				i = maxLen - m.start()
				if i > maxLen / 2:
					res.append(lNow[:i])
					toDo.append(lNow[i:])
					done = True
				break
			if not done:
				res.append(lNow[:maxLen])
				toDo.append(lNow[maxLen:])
	return res


def maybeJoinStr(value):
	"""If a string was splitted in multiple lines joins it again"""
	t = type(value)
	if issubclass(t, str) or issubclass(t, bytes):
		return value
	return "".join(value)


def writeStrMaybeList(outF, value, indent=0, maxLen=115):
	"""Writes out a string, or a list of strings taking care of escaping it for json.
	Lists of strings are indented with a string per line."""
	t = type(value)
	if issubclass(t, str) or issubclass(t, bytes):
		json.dump(value, outF)
	else:
		newline = ",\n" + (indent + 2) * " "
		first = True
		outF.write("[")
		for l in value:
			if first:
				outF.write(newline[1:])
				first = False
			else:
				outF.write(newline)
			json.dump(l, outF)
		outF.write(" ]")


class MetaType(Enum):
	"""the various valid values of meta type"""
	type_dimension = "type-dimension"
	type_value = "type-value"
	type_abstract = "type-abstract"
	type_section = "type-section"


class MetaInfoBase(BaseModel):
	"""Base values for all meta infos"""
	meta_name: str
	meta_type: MetaType
	meta_description: Union[str, List[str]]
	meta_deprecated: bool = False
	meta_abstract_types: List[str] = []

	def standardize(self, compact=False):
		"""Standardizes the values stored (mainly the description formatting)"""
		if compact:
			self.meta_description = maybeJoinStr(self.meta_description)
		else:
			self.meta_description = splitStr(maybeJoinStr(self.meta_description))

	def writeInternal(self, outF, indent):
		pass

	def write(self, outF, indent=0):
		ii = (indent + 2) * " "
		outF.write("""{{
{ii}"meta_name": {meta_name},
{ii}"meta_type": {meta_type},
{ii}"meta_description": """.format(
			ii=ii, meta_name=jd(self.meta_name), meta_type=jd(self.meta_type.value)))
		writeStrMaybeList(outF, self.meta_description, indent=indent + 2)
		if self.meta_deprecated:
			outF.write(',\n{ii}"meta_deprecated": {meta_deprecated}'.format(
				ii=ii, meta_deprecated=jd(self.meta_deprecated)))
		if self.meta_abstract_types:
			outF.write(',\n{ii}"meta_abstract_types": {value}'.format(
				ii=ii, value=jd(self.meta_abstract_types)))
		self.writeInternal(outF, indent)
		outF.write('\n' + (indent * ' ') + '}')

	def __repr__(self):
		outF = io.StringIO()
		outF.write(str(self.__class__))
		self.write(outF)
		return outF.getvalue()

	def __str__(self):
		outF = io.StringIO()
		self.write(outF)
		return outF.getvalue()

	@staticmethod
	def fromDict(d):
		"""initializes a meta info value of the correct subclass from a dictionary"""
		try:
			mtype = MetaType(d.get('meta_type', 'type-value'))
		except:
			raise Exception(
				f"Failed to instantiate meta_info_entry, invalid meta_type '{d.get(meta_type)}''"
			)
		dd = {k: v for k, v in d.items()}
		if isinstance(dd.get('meta_chosen_key'), str):
			dd['meta_chosen_key'] = [dd['meta_chosen_key']]
		if isinstance(dd.get('meta_context_identifiers'), str):
			dd['meta_context_identifiers'] = [dd['meta_context_identifiers']]
		try:
			if mtype == MetaType.type_value:
				el = MetaValue(**dd)
			elif mtype == MetaType.type_abstract:
				el = MetaAbstract(**dd)
			elif mtype == MetaType.type_section:
				el = MetaSection(**dd)
			elif mtype == MetaType.type_dimension:
				el = MetaDimensionValue(**dd)
		except:
			raise Exception(
				f"Failed to instantiate meta_info_entry of type {mtype} from {dd}")
		return el


class MetaEnum(BaseModel):
	"""gives the valid enum values that can be assumed"""
	meta_enum_value: str
	meta_enum_description: Union[str, List[str]]

	def standardize(self, compact=False):
		"""Standardizes the values stored (mainly the description formatting)"""
		if compact:
			self.meta_enum_description = maybeJoinStr(self.meta_enum_description)
		else:
			self.meta_enum_description = splitStr(
				maybeJoinStr(self.meta_enum_description))

	def write(self, outF, indent=0):
		"""Reproducible pretty print of meta enum to json"""
		ii = (indent + 2) * " "
		outF.write("""{{
{ii}"meta_enum_value": {value},
{ii}"meta_enum_description": """.format(ii=ii, value=jd(self.meta_enum_value)))
		writeStrMaybeList(outF, self.meta_enum_description, indent=indent + 2)
		outF.write("\n" + (indent * " ") + "}")


class MetaQueryEnum(BaseModel):
	"""represents the enum values that one can write in a query.
	These can be a superset of the one stored, to allow for alternate spellings,..."""
	meta_query_expansion: str
	meta_query_values: Optional[List[str]]
	meta_query_regexp: Optional[str]

	def write(self, outF, indent=0):
		"""Reproducible pretty print of meta query to json"""
		ii = (indent + 2) * " "
		outF.write(
			"""{{
{ii}"meta_query_expansion": {meta_query_expansion}"""
			.format(ii=ii, meta_query_expansion=jd(self.meta_query_expansion)))
		if self.meta_query_values:
			outF.write(',\n{ii}"meta_query_values": {meta_query_values}'.format(
				ii=ii, meta_query_values=jd(self.meta_query_values)))
		if self.meta_query_regexp:
			outF.write(',\n{ii}"meta_query_regexp": {value}'.format(
				ii=ii, value=jd(self.meta_query_regexp)))
		outF.write("\n" + (indent * " ") + "}")


class MetaRangeKind(Enum):
	"""The valid meta_range_kind values"""
	abs_value = "abs-value"  # The range is for the absolute value of the scalar value (or every component for arrays)
	norm2 = "norm2"  # The range is for the euclidean norm of the value
	utf8_length = "utf8-length"  # The length of the string value using utf-8 encoding
	repetitions = "repetitions"  # The number of repetitions for a repeating value


class MetaRange(BaseModel):
	'''Describes the expected range of the values (constraints on the values)'''
	meta_range_kind: MetaRangeKind
	meta_range_minimum: Optional[float]
	meta_range_maximum: Optional[float]
	meta_range_units: Optional[str]

	def write(self, outF, indent=0):
		"""Reproducible pretty print of meta range to json"""
		ii = (indent + 2) * " "
		outF.write("""{{
{ii}"meta_range_kind": {value}"""
													.format(ii=ii, value=jd(self.meta_range_kind.value)))
		if self.meta_range_minimum is not None:
			outF.write(',\n{ii}"meta_range_minimum": {value}'.format(
				ii=ii, value=jd(self.meta_range_minimum)))
		if self.meta_range_maximum is not None:
			outF.write(',\n{ii}"meta_range_maximum": {value}'.format(
				ii=ii, value=jd(self.meta_range_maximum)))
		if self.meta_range_units:
			outF.write(',\n{ii}"meta_range_units": {value}'.format(
				ii=ii, value=jd(self.meta_range_units)))
		outF.write("\n" + (indent * " ") + "}")


class MetaDataType(Enum):
	"""The different data types corresponding to a meta value"""
	Int = "int"
	Int32 = "int32"
	Int64 = "int64"
	Boolean = "boolean"
	Reference = "reference"
	Float32 = "float32"
	Float = "float"
	Float64 = "float64"
	String = "string"
	Binary = "binary"
	Json = "json"


class MetaDimension(BaseModel):
	"""Defines a dimension of the (multi) dimensional array of a value of a meta_info_entry"""
	meta_dimension_fixed: Optional[int]
	meta_dimension_symbolic: Optional[str]

	#@validator('meta_dimension_symbolic')
	def either_defined_not_both(cls, v, values, **kwargs):
		if "meta_dimension_fixed" in values:
			if values["meta_dimension_fixed"] is not None:
				if v:
					raise ValueError(
						'only one of meta_dimension_fixed and meta_dimension_symbolic should be defined, not both ({vFix}, {v})'.
						format(vFix=jd(values["meta_dimension_fixed"]), v=jd(v)))
			elif v is None:
				raise ValueError(
					'One of meta_dimension_fixed or meta_dimension_symbolic should be defined (none given)'
				)
		return v

	def write(self, outF, indent=0):
		"""Reproducible pretty print of meta dimension to json"""
		ii = (indent + 2) * " "
		outF.write("{")
		comma = ''
		if self.meta_dimension_fixed is not None:
			outF.write('{comma}\n{ii}"meta_dimension_fixed": {value}'.format(
				ii=ii, comma=comma, value=jd(self.meta_dimension_fixed)))
			comma = ','
		if self.meta_dimension_symbolic:
			outF.write('{comma}\n{ii}"meta_dimension_symbolic": {value}'.format(
				ii=ii, comma=comma, value=jd(self.meta_dimension_symbolic)))
		outF.write("\n" + (indent * " ") + "}")


class MetaDimensionValue(MetaInfoBase):
	meta_type = MetaType.type_dimension
	meta_data_type: Optional[MetaDataType]
	meta_parent_section: str

	def writeInternal(self, outF, indent):
		ii = (indent + 2) * ' '
		outF.write(',\n{ii}"meta_parent_section": {value}'.format(
			ii=ii, value=jd(self.meta_parent_section)))
		if self.meta_data_type:
			outF.write(',\n{ii}"meta_data_type": {value}'.format(
				ii=ii, value=jd(self.meta_data_type.value)))


class MetaValue(MetaInfoBase):
	meta_type = MetaType.type_value
	meta_parent_section: str
	meta_data_type: MetaDataType
	meta_repeats: bool = False
	meta_required: bool = False
	meta_referenced_section: Optional[str]
	meta_dimension: List[MetaDimension] = []
	meta_default_value: Optional[str]
	meta_enum: Optional[List[MetaEnum]]
	meta_query_enum: Optional[List[MetaQueryEnum]]
	meta_range_expected: Optional[List[MetaRange]]
	meta_units: Optional[str]

	def standardize(self, compact=False):
		super().standardize(compact=compact)
		if self.meta_enum:
			for e in self.meta_enum:
				e.standardize(compact=compact)

	def writeInternal(self, outF, indent):
		ii = (indent + 2) * ' '
		outF.write(',\n{ii}"meta_parent_section": {value}'.format(
			ii=ii, value=jd(self.meta_parent_section)))
		if self.meta_data_type:
			outF.write(',\n{ii}"meta_data_type": {value}'.format(
				ii=ii, value=jd(self.meta_data_type.value)))
		outF.write(
			',\n{ii}"meta_repeats": {value}'.format(ii=ii, value=jd(self.meta_repeats)))
		outF.write(',\n{ii}"meta_required": {value}'.format(
			ii=ii, value=jd(self.meta_required)))
		if self.meta_referenced_section:
			outF.write(',\n{ii}"meta_referenced_section": {value}'.format(
				ii=ii, value=jd(self.meta_referenced_section)))
		outF.write(f',\n{ii}"meta_dimension": [ ')
		first = True
		for dim in self.meta_dimension:
			if first:
				first = False
			else:
				outF.write(', ')
			dim.write(outF, indent + 2)
		outF.write(' ]')
		if self.meta_default_value is not None:
			outF.write(',\n{ii}"meta_default_value": {value}'.format(
				ii=ii, value=jd(self.meta_default_value)))
		first = True
		if self.meta_enum is not None:
			outF.write(',\n{ii}"meta_enum": [ '.format(ii=ii))
			for e in self.meta_enum:
				if first:
					first = False
				else:
					outF.write(', ')
				e.write(outF, indent=indent + 4)
			outF.write(' ]')
		first = True
		if self.meta_query_enum is not None:
			outF.write(',\n{ii}"meta_query_enum": [ '.format(ii=ii))
			for el in self.meta_query_enum:
				if first:
					first = False
				else:
					outF.write(', ')
				el.write(outF, indent=indent + 4)
			outF.write(' ]')
		first = True
		if self.meta_range_expected is not None:
			outF.write(',\n{ii}"meta_range_expected": [ '.format(ii=ii))
			for el in self.meta_range_expected:
				if first:
					first = False
				else:
					outF.write(', ')
				el.write(outF, indent=indent + 4)
			outF.write(' ]')
		if self.meta_units:
			outF.write(
				',\n{ii}"meta_units": {value}'.format(ii=ii, value=jd(self.meta_units)))


class MetaSection(MetaInfoBase):
	meta_type = MetaType.type_section
	meta_parent_section: Optional[str]
	meta_repeats: bool = True
	meta_required: bool = False
	meta_chosen_key: Optional[List[str]]
	meta_context_identifier: Optional[List[str]]
	meta_contains: Optional[List[str]]

	def writeInternal(self, outF, indent):
		ii = (indent + 2) * ' '
		outF.write(',\n{ii}"meta_parent_section": {value}'.format(
			ii=ii, value=jd(self.meta_parent_section)))
		outF.write(
			',\n{ii}"meta_repeats": {value}'.format(ii=ii, value=jd(self.meta_repeats)))
		outF.write(',\n{ii}"meta_required": {value}'.format(
			ii=ii, value=jd(self.meta_required)))
		if self.meta_chosen_key:
			outF.write(',\n{ii}"meta_chosen_key": {value}'.format(
				ii=ii, value=jd(self.meta_chosen_key)))
		if self.meta_context_identifier:
			outF.write(',\n{ii}"meta_context_identifier": {value}'.format(
				ii=ii, value=jd(self.meta_context_identifier)))
		if self.meta_contains:
			outF.write(',\n{ii}"meta_contains": {value}'.format(
				ii=ii, value=jd(self.meta_contains)))


class MetaAbstract(MetaInfoBase):
	meta_type = MetaType.type_abstract


MetaInfoEntry = Union[MetaDimensionValue, MetaValue, MetaSection, MetaAbstract]


class MetadictRequire(BaseModel):
	metadict_required_name: str
	metadict_required_version: Optional[str]

	def write(self, outF, indent=0):
		"""reproducible pretty print to json"""
		ii = (indent + 2) * ' '
		outF.write('{{\n{ii}"metadict_required_name": {value}'.format(
			ii=ii, value=jd(self.metadict_required_name)))
		if self.metadict_required_version is not None:
			outF.write(',\n{ii}"metadict_required_version": {value}'.format(
				ii=ii, value=jd(self.metadict_required_version)))
		outF.write('\n' + (indent * ' ') + '}')


class MetaDictionary(BaseModel):
	metadict_name: str
	metadict_source: Optional[List[str]]
	metadict_description: Union[str, List[str]]
	metadict_version: Optional[str]
	metadict_require: List[MetadictRequire] = []
	meta_info_entry: List[MetaInfoEntry] = []
	meta_info_entries_cache: Optional[Dict[str, List[MetaInfoEntry]]]

	@property
	def meta_info_entries(self):
		if self.meta_info_entries_cache is not None and len(
				self.meta_info_entries_cache) == len(self.meta_info_entry):
			return self.meta_info_entries_cache
		entries = {}
		for el in self.meta_info_entry:
			entries[el.meta_name] = entries.get(el.meta_name, []) + [el]
		self.meta_info_entries_cache = entries
		return entries

	def __getitem__(self, meta_name):
		"""returns a list with the meta_info_entry with the given meta_name.
		If meta_name does not exist, it returns an empty list"""
		return self.meta_info_entries.get(meta_name, [])

	def findOne(self, metaName, metaType):
		"""Finds the entries with type meta_type with the given name.
		Raises an exception if not exactly one entry is found."""
		entries = [e for e in self[metaName] if e.meta_type == metaType]
		if len(entries) == 1:
			return entries[0]
		elif not entries:
			raise Exception(
				f'Expected one {metaName} of type {metaType.value}, but found none.')
		else:
			raise Exception(
				f'Expected just one {metaName} of type {metaType.value}, not {len(entries)}: {entries}'
			)

	def standardize(self, compact=False):
		"""standarizes the dictionary (mostly the description entries).
		If compact is true each description is folded in a single string, otherwise a lit of strings (with reasonable line breaks) is used."""
		if compact:
			self.metadict_description = maybeJoinStr(self.metadict_description)
		else:
			self.metadict_description = splitStr(
				maybeJoinStr(self.metadict_description))
		for el in self.meta_info_entry:
			el.standardize(compact=compact)
		self.meta_info_entry.sort(key=lambda x: x.meta_name)

	def write(self,
											outF,
											indent=0,
											writeName=True,
											writeSource=False,
											writeMetaInfoEntries=True):
		"""Writes out a dictionary as an indented json. The same json is produced for the same dictionary, but you should call standardize if you want to avoid trivial differences (different order of meta_info_entries, different split of description strings)"""
		outF.write("{")
		ii = (indent + 2) * ' '
		comma = ''
		if writeName:
			outF.write('{comma}\n{ii}"metadict_name": {value}'.format(
				ii=ii, comma=comma, value=jd(self.metadict_name)))
			comma = ','
		if writeSource:
			outF.write('{comma}\n{ii}"metadict_source": {value}'.format(
				ii=ii, comma=comma, value=jd(self.metadict_source)))
			comma = ','
		outF.write(
			'{comma}\n{ii}"metadict_description": '.format(ii=ii, comma=comma))
		writeStrMaybeList(outF, self.metadict_description, indent=indent + 2)
		if self.metadict_version is not None:
			outF.write(',\n{ii}"metadict_version": {value}'.format(
				ii=ii, value=jd(self.metadict_version)))
		outF.write(f',\n{ii}"metadict_require": [ ')
		first = True
		for el in self.metadict_require:
			if first:
				first = False
			else:
				outF.write(', ')
			el.write(outF, indent=indent + 4)
		outF.write(" ]")
		if writeMetaInfoEntries:
			outF.write(f',\n{ii}"meta_info_entry": [ ')
			first = True
			for el in self.meta_info_entry:
				if first:
					first = False
				else:
					outF.write(', ')
				el.write(outF, indent=indent + 4)
			outF.write(' ]')
		outF.write('\n' + (indent * ' ') + '}')

	def writeExploded(self, basePath, cleanup=True):
		"""Writes an exploded dictionary at the given path"""
		dir = os.path.join(basePath, self.metadict_name + '.meta_dictionary')
		if not os.path.isdir(dir):
			os.makedirs(dir)
		writeFile(
			os.path.join(dir, "_.meta_dictionary.json"),
			lambda fOut: self.write(fOut, writeMetaInfoEntries=False))
		present = {f for f in os.listdir(dir) if f.endswith('.meta_info_entry.json')}
		written = set()
		for el in self.meta_info_entry:
			fName = el.meta_name + '.meta_info_entry.json'
			written.add(fName)
			writeFile(os.path.join(dir, fName), lambda outF: el.write(outF))
		timestamp = date.today().isoformat()
		safeRemove(present.difference(written))

	@classmethod
	def fromDict(cls, d):
		"""Initializes a meta_dictionary from a dictionary (for example from json serialization)"""
		try:
			metadict_name = d.get("metadict_name")
			metadict_source = d.get("metadict_source")
			metadict_description = d.get("metadict_description", "")
			metadict_version = d.get("metadict_version")
			metadict_require = [
				MetadictRequire(**x) for x in d.get("metadict_require", [])
			]
		except:
			dd = {k: v for k, v in d.items() if k != "meta_info_entry"}
			raise Exception(f"failed to get metadict attributes from {dd}")
		d_meta_info_entry = d.get("meta_info_entry", [])
		meta_info_entry = []
		for e in d_meta_info_entry:
			meta_info_entry.append(MetaInfoBase.fromDict(e))
		return cls(
			metadict_name=metadict_name,
			metadict_source=metadict_source,
			metadict_description=metadict_description,
			metadict_version=metadict_version,
			metadict_require=metadict_require,
			meta_info_entry=meta_info_entry)

	@classmethod
	def loadDictionaryAtPath(cls, p, name=None):
		"""Loads a single json file dictionary from the given path"""
		try:
			if not name:
				name = os.path.basename(p)
				if name.endswith('.json'):
					name = name[:-len('.json')]
				if name.endswith('.meta_dictionary'):
					name = name[:-len('.meta_dictionary')]
			d = json.load(open(p, encoding='utf8'))
			if d.get('metadict_name', name) != name:
				raise Exception(
					f'metadict at {p} has unexpected name ({d["metadict_name"]})')
			d['metadict_name'] = name
			p2 = os.path.realpath(os.path.abspath(p))
			uris = d.get('metadict_source', [])
			for pp in [p, p2]:
				uri = 'file://' + pp
				if not uri in uris:
					uris.insert(0, uri)
			d['metadict_source'] = uris
			return cls.fromDict(d)
		except:
			raise Exception(f'failure loading dictionary at "{p}"')

	@classmethod
	def fileLoader(cls, paths: List[str]):
		"""Defines a loader function that looks for dictionaries at the given paths"""

		def find(name):
			for basep in paths:
				jsonP = os.path.join(basep, name + ".meta_dictionary.json")
				explodedP = os.path.join(basep, name + ".meta_dictionary")
				for p in [jsonP, explodedP]:
					if os.path.exists(p):
						return cls.loadAtPath(p, name=name)
			raise Exception(f'could not find dictionary {name} in {paths}')

		return find

	@classmethod
	def loadExplodedDictionaryAtPath(cls, path):
		"""Loads an exploded dictionary that lives inside the directory *.meta_dictionary diven at path"""
		expectedName = os.path.basename(path)
		if expectedName in ['.', '..']:
			expectedName = os.path.basename(os.path.normpath(os.path.abspath(path)))
		if expectedName.endswith('.meta_dictionary'):
			expectedName = expectedName[:-len('.meta_dictionary')]
		baseInfoPath = os.path.join(path, '_.meta_dictionary.json')
		if not os.path.isfile(baseInfoPath):
			raise Exception(
				f'Exploded dictionary is missing base info at {baseInfoPath}')
		with open(baseInfoPath, encoding='utf8') as fIn:
			try:
				baseDict = json.load(fIn)
			except:
				raise Exception(f'Invalid json in {baseInfoPath}')
		baseDict['metadict_name'] = baseDict.get('metadict_name', expectedName)
		if baseDict['metadict_name'] != expectedName:
			logging.warn(
				f'Inconsistent dictionary name from filename {expectedName} vs {baseDict["metadict_name"]} in {baseInfoPath}'
			)
		p2 = os.path.realpath(os.path.abspath(path))
		uris = baseDict.get('metadict_source', [])
		for pp in [path, p2]:
			uri = 'file://' + pp
			if not uri in uris:
				uris.insert(0, uri)
		baseDict['metadict_source'] = uris
		entriesNames = [
			f for f in os.listdir(path) if f.endswith('.meta_info_entry.json')
		]
		entries = []
		for f in entriesNames:
			entryExpectedName = f[:-len('.meta_info_entry_json')]
			entryPath = os.path.join(path, f)
			with open(entryPath, encoding='utf8') as fIn:
				try:
					d = json.load(fIn)
				except:
					raise Exception(f'Invalid json in {entryPath}')
			d['meta_name'] = d.get('meta_name', entryExpectedName)
			if d['meta_name'] != entryExpectedName:
				logging.warn(
					f'Inconsistent entry name from filename {entryExpectedName} vs {d["meta_name"]} in {entryPath}'
				)
			entries.append(d)
		entries.sort(key=lambda x: x.get('meta_name'))
		baseDict['meta_info_entry'] = entries
		try:
			return cls.fromDict(baseDict)
		except:
			raise Exception(f'failure loading exploded dictionary at "{path}"')

	@classmethod
	def loadAtPath(cls, path):
		"""loads the dictionary at the given path (automatically detecting its type)"""
		if path.endswith('/') or os.path.basename(path) == '_.meta_dictionary.json':
			dPath = os.path.dirname(path)
			if not dPath:
				dPath = '.'
			return cls.loadExplodedDictionaryAtPath(dPath)
		elif path.endswith('.meta_dictionary.json'):
			return cls.loadDictionaryAtPath(path)
		elif path.endswith('.meta_dictionary'):
			return cls.loadExplodedDictionaryAtPath(path)
		else:
			raise Exception(
				f'Do not know how to interpret file {path}, expected either a file *.meta_dictionary.json or  directory *.meta_dictionary'
			)


class MetaInfo(BaseModel):
	"""Represents a set of dictionaries that are used together"""
	dictionaries: Dict[str, MetaDictionary]
	metaNameInDicts: Dict[str, Set[str]]

	def findMany(self, metaName, metaType=None, dictionaryNames=None):
		"""Finds all entries with the given name, and returns a list of (entry,dinctionaryName) tuples.
		If metaType or dictionaryNames are given, filters them accordingly."""
		res = []
		for dictName in self.metaNameInDicts.get(metaName, set()):
			if not dictionaryNames or dictName in dictionaryNames:
				dict = self.dictionaries[dictName]
				for entry in dict[metaName]:
					if not metaType or entry.meta_type == metaType:
						res.append(EntryDict(entry, dictName))
		return res

	def findOne(self, metaName, metaType=None, dictionaryNames=None):
		"""Finds the entries with type meta_type with the given name.
		If dictionaryNames are given restricts the search to those dictionaries.
		Raises an exception if none or more than one entries are found."""
		entries = self.findMany(metaName, metaType, dictionaryNames)
		if len(entries) == 1:
			return entries[0]
		elif not entries:
			raise Exception(
				f'Expected one {metaName} of type {metaType.value}, but none found.')
		else:
			raise Exception(
				f'Expected just one {metaName} of type {metaType.value}, not {len(entries)}: {entries}'
			)

	def findSection(self, metaName, dictionaryNames=None):
		"""Finds the section with the given name.
		If dictionaryNames are given restricts the search to those dictionaries.
		Raises an exception if more than one entries are found, returns None if none are found."""
		return self.findOne(metaName, MetaType.type_section, dictionaryNames)

	def addMeta(self, metaName, dictName):
		self.metaNameInDicts[metaName] = self.metaNameInDicts.get(
			metaName, set()).union([dictName])

	def addMetaDict(self, metaDict):
		name = metaDict.metadict_name
		if name in self.dictionaries:
			raise Exception(f'dictionary {name} added twice to MetaInfo')
		self.dictionaries[name] = metaDict
		for entry in metaDict.meta_info_entry:
			self.addMeta(entry.meta_name, name)

	def complete(self, loadDictNamed):
		"""Ensures that all dependent dictionaries are loaded"""
		namesDone = set()
		while len(namesDone) < len(self.dictionaries):
			for n, d in self.dictionaries.items():
				if n not in namesDone:
					namesDone.add(n)
					for dep in d.metadict_require:
						name = dep.metadict_required_name
						if name not in self.dictionaries:
							newD = loadDictNamed(name)
							self.dictionaries[name] = newD
						version = self.dictionaries[name].metadict_version
						expectedVersion = dep.metadict_required_version
						if expectedVersion and expectedVersion != version:
							raise Exception(
								f"Unexpected version {version} for dictionary {name} when {d.metadict_name} expects version {expectedVersion}"
							)

	def depsOfDict(self, dictName):
		"""returns a set with the names of the dependent dictionaries of dictName (including dictName)"""
		deps = set([dictName])
		depsToDo = set([dictName])
		while depsToDo:
			dictNow = depsToDo.pop()
			d = self.dictionaries.get(dictNow)
			if d is None:
				if dictNow == dictName:
					raise Exception(f"Dictionary named {dictName} is not loaded in MetaInfo")
				else:
					raise Exception(
						f"missing dependency {dictNow} of {dictName}, call complete to load the dependency"
					)
			for dep in d.metadict_require:
				name = dep.metadict_required_name
				if name not in deps:
					deps.add(name)
					depsToDo.add(name)
		return deps

	def loadDictionariesStartingAtPath(self,
																																				dictPath,
																																				extraPaths=None,
																																				loadAll=False):
		"""loads the dictionary at dictPath and all its dependencies (or if loadAll is true, all other dictionaries at the same path)"""
		if dictPath.endswith('/') or os.path.basename(
				dictPath) == '_.meta_dictionary.json':
			basePath = os.path.normpath(os.path.join(os.path.dirname(basePath), '..'))
		else:
			basePath = os.path.dirname(dictPath)
		if not basePath:
			basePath = '.'
		paths = [basePath]
		if extraPaths:
			paths += extraPaths
		loader = MetaDictionary.fileLoader(paths)
		d = MetaDictionary.loadAtPath(dictPath)
		self.addMetaDict(d)
		if loadAll:
			for f in os.listdir(basePath):
				if (
						f.endswith('.meta_dictionary') or
						f.endswith('.meta_dictionary.json')) and f != os.path.basename(dictPath):
					d = MetaDictionary.loadAtPath(os.path.join(basePath, f))
					self.addMetaDict(d)
		self.complete(loader)

	@classmethod
	def withPath(cls, dictPath, extraPaths=None, loadAll=False):
		metaI = cls(dictionaries={}, metaNameInDicts={})
		metaI.loadDictionariesStartingAtPath(
			dictPath=dictPath, extraPaths=extraPaths, loadAll=loadAll)
		return metaI


class MetaSchemaSection(BaseModel):
	dictionary: str
	section: MetaSection
	valueEntries: Dict[str, MetaValue]
	injectedValues: Dict[str, MetaValue]
	subSections: dict  #Dict[str,'MetaSchemaSection']
	injectedSections: dict  #Dict[str,obj]# 'MetaSchemaSection']
	dimensions: Dict[str, MetaDimensionValue]

	def addSubsection(self, subsection):
		""""""
		existingSub = self.subSections.get(subsection.section.meta_name)
		if not existingSub:
			self.subSections[subsection.section.meta_name] = subsection
		elif subsection.section == existingSub.section and subsection.dictionary == existingSub.dictionary:
			raise Exception(
				f'Duplicate add of section {subsection.section.meta_name} {subsection.dictionary}'
			)
		else:
			raise Exception(
				f'Duplicate section {subsection.section.meta_name} in {existingSub.dictionary} and {subsection.dictionary}: {existingSub.section} vs {subsection.section}'
			)

	def addDimension(self, dimension: MetaDimensionValue):
		existingDim = self.dimensions.get(dimension.meta_name)
		if not existingDim:
			self.dimensions[dimension.meta_name] = dimension
		elif dimension == existingDim:
			raise Exception(f'Duplicate add of dimension {dimension}')
		else:
			raise Exception(
				f'Duplicate dimension {dimension.meta_name}: {existingDim} vs {dimension}')

	def addValue(self, value: MetaValue):
		existing = self.valueEntries.get(value.meta_name)
		if not existing:
			self.valueEntries[value.meta_name] = value
		elif value == existing:
			raise Exception(f'Duplicate add of value {value}')
		else:
			raise Exception(
				f'Duplicate dimension {value.meta_name}: {existing} vs {value}')


class MetaSchema(BaseModel):
	metaInfo: MetaInfo
	mainDictionary: str
	dictionaries: Set[str]
	sections: Dict[str, MetaSchemaSection]
	abstractTypes: Dict[str, MetaAbstract]
	dimensions: Dict[str, MetaDimensionValue]

	def findMany(self, metaName, metaType=None):
		return self.metaInfo.findMany(metaName, metaType, self.dictionaries)

	def findOne(self, metaName, metaType=None):
		return self.metaInfo.findOne(metaName, metaType, self.dictionaries)

	def ensureSection(self, sectionName):
		"""Ensures that the section with the given name is in the schema (and all its super sections), and returns the corresponding MetaSchemaSection"""
		sAttName = sectionName
		sectionPath = []
		sectionPathNames = []
		while sAttName:
			if sAttName in sectionPathNames:
				raise Exception(f'circular ref back to {sAttName} after {superDone}')
			sAtt = self.metaInfo.findSection(
				sAttName, dictionaryNames=self.dictionaries)
			existingSection = self.sections.get(sAttName)
			if not existingSection:
				newSection = MetaSchemaSection(
					dictionary=sAtt.metadict_name,
					section=sAtt.meta_info_entry,
					valueEntries={},
					injectedSections={},
					injectedValues={},
					subSections={},
					dimensions={})
				self.sections[sAttName] = newSection
				if sectionPath:
					newSection.addSubsection(sectionPath[-1])
				sectionPath.append(newSection)
				sectionPathNames.append(sAttName)
				sAttName = sAtt.meta_info_entry.meta_parent_section
			else:
				if sectionPath:
					existingSection.addSubsection(sectionPath[-1])
				sectionPath.append(existingSection)
				break
		return sectionPath[0]

	def addSchemaOfDictionary(self, dict: MetaDictionary):
		for entry in dict.meta_info_entry:
			meta_type = entry.meta_type
			if meta_type == MetaType.type_abstract:
				existingEntry = self.abstractTypes.get(entry.meta_name)
				if not existingEntry:
					self.abstracyTypes[entry.meta_name] = entry
				elif existingEntry != entry:
					raise Exception(
						f'Duplicated abstract type {entry.meta_name}: {entry} vs {existingEntry}')
				else:
					raise Exception(
						f'Duplicated add of abstract type {entry.meta_name}')  # ignore?
			elif meta_type == MetaType.type_dimension:
				existingEntry = self.dimensions.get(entry.meta_name)
				if not existingEntry:
					self.abstracyTypes[entry.meta_name] = entry
					self.ensureSection(entry.meta_parent_section).addDimension(entry)
				elif existingEntry != entry:
					raise Exception(
						f'Duplicated dimension {entry.meta_name}: {entry} vs {existingEntry}')
				else:
					raise Exception(
						f'Duplicated add of abstract type {entry.meta_name}')  # ignore
			elif meta_type == MetaType.type_section:
				self.ensureSection(entry.meta_name)
			elif meta_type == MetaType.type_value:
				sec = self.ensureSection(entry.meta_parent_section)
				sec.addValue(entry)
			else:
				raise Exception(
					f'Unexpected meta_type {meta_type} in entry {entry.meta_name} of dictionary {dict.metadict_name}'
				)

	def extendToDictionary(self, newDictName: str):
		"""Modifies this dictionary adding the missing dependencies of newDictName
		The result is equivalent to forDictionary(newDictName) only if self.mainDictionary is in the dependencies of newDictName"""
		newDeps = self.metaInfo.depsOfDict(newDictName)
		oldDeps = self.dictionaries
		toDo = newDeps
		if oldDeps.difference(newDeps):
			logging.warn(
				f'extendending {self.mainDictionary} to {newDictName} that is not a superset will leave extra dictionaries in the schema'
			)
		self.dictionaries = self.dictionaries.union(newDeps)
		self.mainDictionary = newDictName
		for d in toDo:
			dict = metaInfo.dictionaries[d]
			self.addSchemaOfDictionary(dict)
		return self

	@classmethod
	def forDictionary(cls, dictName: str, metaInfo: MetaInfo):
		deps = metaInfo.depsOfDict(dictName)
		schema = MetaSchema(
			metaInfo=metaInfo,
			mainDictionary=dictName,
			dictionaries=deps,
			sections={},
			abstractTypes={},
			dimensions={})
		for dep in deps:
			dict = metaInfo.dictionaries[dep]
			schema.addSchemaOfDictionary(dict)
		return schema

