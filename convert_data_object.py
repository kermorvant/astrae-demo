import json
import re
import ast
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from datetime import datetime
from arkindex_export import open_database, Element, Metadata as DBMetadata, Transcription
from arkindex_export.queries import list_children
from arkindex_export.models import ElementPath
from pathlib import Path

@dataclass
class Source:
    method: str               # "manual", "ai", "ocr", "import"
    agent: Optional[str] = None   # user id, model name (e.g. "gliner-base")
    confidence: Optional[float] = None

@dataclass
class IIIFRegion:
    x: int
    y: int
    width: int
    height: int
    rotation_angle: int
    source: Optional[Source] = None

@dataclass  
class Metadata:
    name: str
    value: str
    type: str
    source: Optional[Source] = None

@dataclass
class Concept:
    id: str
    label: str
    vocabulary: str
    pyramid_level: int
    external_id: Optional[str] = None
    source: Optional[Source] = None

@dataclass
class ConceptMention:
    concept_id: str
    element_id: str
    offset: Optional[int] = None
    length: Optional[int] = None
    source: Optional[Source] = None

@dataclass
class View:
    id: str
    document_id: str
    iiif_base: str
    region: IIIFRegion
    name: str

@dataclass
class Paragraph:
    id: str
    view_id: str
    region: IIIFRegion
    text: str
    text_source: Optional[Source] = None
    concepts: List[Concept] = field(default_factory=list)
    concept_mentions: List[ConceptMention] = field(default_factory=list)

@dataclass
class Illustration:
    id: str
    view_id: str
    region: IIIFRegion
    description: str
    description_source: Optional[Source] = None
    metadata: List[Metadata] = field(default_factory=list)
    concepts: List[Concept] = field(default_factory=list)
    concept_mentions: List[ConceptMention] = field(default_factory=list)

@dataclass
class ArtWork:
    id: str
    iiif_base: str
    region: IIIFRegion
    description: str
    description_source: Optional[Source] = None
    metadata: List[Metadata] = field(default_factory=list)
    concepts: List[Concept] = field(default_factory=list)
    concept_mentions: List[ConceptMention] = field(default_factory=list)

@dataclass
class Document:
    id: str
    title: str
    creator: str
    date: datetime
    metadata: List[Metadata] = field(default_factory=list)

class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def get_region_obj(element, source: Optional[Source] = None) -> IIIFRegion:
    polygon_points_str = element.polygon
    if not polygon_points_str:
        return IIIFRegion(x=0, y=0, width=0, height=0, rotation_angle=0, source=source)
    polygon_points = ast.literal_eval(polygon_points_str)
    x_coords = [point[0] for point in polygon_points]
    y_coords = [point[1] for point in polygon_points]
    x_min = min(x_coords)
    x_max = max(x_coords)
    y_min = min(y_coords)
    y_max = max(y_coords)
    width = x_max - x_min
    height = y_max - y_min
    return IIIFRegion(
        x=x_min,
        y=y_min,
        width=width,
        height=height,
        rotation_angle=element.rotation_angle or 0,
        source=source
    )

def iconclass_to_pyramid_level(code: str) -> int:
    if code.startswith("31"):
        return 5   # humans
    if code.startswith("14"):
        return 5   # animals
    if code.startswith("41A"):
        return 5   # objects / furniture
    if code.startswith("41D"):
        return 5   # clothing
    if code.startswith("41B"):
        return 6   # architectural setting
    if code.startswith("25"):
        return 6   # landscape / lighting
    return 5

def main():
    open_database(Path("astrae-collection-20260310-220013.sqlite"))

    try:
        from iconclass import init as iconclass_init
        ic = iconclass_init()
    except ImportError:
        ic = None

    CONFIG_ID = '273da36d-a36a-46ba-8325-752ed5ff6c3b'
    ICONCLASS_RE = re.compile(r'\(\s*\d+[A-Z0-9, +\-]*(?:\([^\)]*\))?\s*\)')

    documents_map = {}
    print("Extracting documents...")
    for doc_el in Element.select().where(Element.type == 'document'):
        metas_db = list(DBMetadata.select().where(DBMetadata.element_id == doc_el.id))
        metas_dict = {m.name.lower(): m.value for m in metas_db}
        
        title = metas_dict.get('title', metas_dict.get('titre', doc_el.name))
        creator = metas_dict.get('creator', metas_dict.get('auteur', metas_dict.get('author', 'unk')))
        date_str = metas_dict.get('date', 'unk')
        
        parsed_date = datetime.now() # Fallback if unparsable
        if date_str != 'unk':
            try:
                parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                pass
        
        metas_list = [Metadata(name=m.name, value=m.value, type=m.type, source=Source(method="manual")) for m in metas_db]
        
        doc = Document(
            id=doc_el.id,
            title=title,
            creator=creator,
            date=parsed_date,
            metadata=metas_list
        )
        documents_map[doc_el.id] = doc

    page_to_doc = {}
    for path in ElementPath.select():
        if path.parent_id in documents_map:
            page_to_doc[path.child_id] = path.parent_id

    data = []
    views_list = []

    print("Extracting pages, paragraphs, and illustrations...")
    for page in Element.select().where(Element.type == 'page'):
        doc_id = page_to_doc.get(page.id, "unknown_doc")
        
        view = View(
            id=page.id,
            document_id=doc_id,
            iiif_base=page.image.url if page.image else "",
            region=get_region_obj(page),
            name=page.name
        )
        views_list.append(view)

        for element in list_children(page.id).where((Element.type == 'paragraph') | (Element.type == 'illustration')):
            transcriptions = Transcription.select().where(Transcription.element==element.id)
            transcription_text = ""
            
            concepts = []
            concept_mentions = []
            
            if element.type == 'paragraph':
                if transcriptions.count() > 0:
                    transcription_text = transcriptions[0].text
            else:
                for t in transcriptions:
                    if t.worker_run and t.worker_run.configuration_id == CONFIG_ID:
                        # Extract iconclass tags before stripping
                        if ic:
                            matches = ICONCLASS_RE.findall(t.text)
                            for mx in matches:
                                ic_code = mx.strip('() ')
                                try:
                                    ic_obj = ic[ic_code]
                                    lbl = ic_obj('en') if hasattr(ic_obj, '__call__') else ic_code
                                except Exception:
                                    lbl = ic_code
                                
                                cid = f"iconclass_{ic_code}"
                                if not any(c.id == cid for c in concepts):
                                    concepts.append(Concept(
                                        id=cid,
                                        label=lbl,
                                        vocabulary="iconclass",
                                        pyramid_level=iconclass_to_pyramid_level(ic_code),
                                        external_id=ic_code,
                                        source=Source(method="genai", agent="gemini-2.5-flash")
                                    ))
                                concept_mentions.append(ConceptMention(
                                    concept_id=cid,
                                    element_id=element.id
                                ))
                        
                        clean_text = ICONCLASS_RE.sub('', t.text)
                        transcription_text = ' '.join(clean_text.split())
                        break
            
            if element.type == 'paragraph':
                text_src = Source(method="ocr", agent="microsoft_ocr") if transcription_text else None
                p = Paragraph(
                    id=element.id,
                    view_id=view.id,
                    region=get_region_obj(element),
                    text=transcription_text,
                    text_source=text_src,
                    concepts=concepts,
                    concept_mentions=concept_mentions
                )
                data.append({'type': 'paragraph', **asdict(p)})
            elif element.type == 'illustration':
                reg_src = Source(method="cv", agent="yolo")
                metas = [Metadata(name=m.name, value=m.value, type=m.type, source=Source(method="manual")) for m in DBMetadata.select().where(DBMetadata.element_id == element.id)]
                i = Illustration(
                    id=element.id,
                    view_id=view.id,
                    region=get_region_obj(element, source=reg_src),
                    description=transcription_text,
                    metadata=metas,
                    concepts=concepts,
                    concept_mentions=concept_mentions
                )
                data.append({'type': 'illustration', **asdict(i)})

    print("Extracting paintings (ArtWork)...")
    for painting in Element.select().where(Element.type == 'painting'):
        transcriptions = Transcription.select().where(Transcription.element==painting.id)
        transcription_text = ""
        concepts = []
        concept_mentions = []
        
        for t in transcriptions:
            if t.worker_run and t.worker_run.configuration_id == CONFIG_ID:
                if ic:
                    matches = ICONCLASS_RE.findall(t.text)
                    for mx in matches:
                        ic_code = mx.strip('() ')
                        try:
                            ic_obj = ic[ic_code]
                            lbl = ic_obj('en') if hasattr(ic_obj, '__call__') else ic_code
                        except Exception:
                            lbl = ic_code
                        
                        cid = f"iconclass_{ic_code}"
                        if not any(c.id == cid for c in concepts):
                            concepts.append(Concept(
                                id=cid,
                                label=lbl,
                                vocabulary="iconclass",
                                pyramid_level=iconclass_to_pyramid_level(ic_code),
                                external_id=ic_code,
                                source=Source(method="genai", agent="gemini-2.5-flash")
                            ))
                        concept_mentions.append(ConceptMention(
                            concept_id=cid,
                            element_id=painting.id
                        ))
                
                clean_text = ICONCLASS_RE.sub('', t.text)
                transcription_text = ' '.join(clean_text.split())
                break
                
        metas = [Metadata(name=m.name, value=m.value, type=m.type, source=Source(method="manual")) for m in DBMetadata.select().where(DBMetadata.element_id == painting.id)]
        
        a = ArtWork(
            id=painting.id,
            iiif_base=painting.image.url if painting.image else "",
            region=get_region_obj(painting),
            description=transcription_text,
            metadata=metas,
            concepts=concepts,
            concept_mentions=concept_mentions
        )
        data.append({'type': 'painting', **asdict(a)})

    output_data = {
        'documents': [asdict(d) for d in documents_map.values()], 
        'views': [asdict(v) for v in views_list],
        'elements': data
    }

    with open('data_objects.json', 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=4, ensure_ascii=False, cls=CustomEncoder)
    print("Saved to data_objects.json")

if __name__ == "__main__":
    main()
