import json
import typesense
import toml
from typing import Dict, Any

def get_typesense_client():
    secrets = toml.load(".streamlit/secrets.toml")
    client = typesense.Client({
        'nodes': [{
            'host': secrets['TYPESENSE_HOST'],
            'port': secrets['TYPESENSE_PORT'],
            'protocol': secrets['TYPESENSE_PROTOCOL']
        }],
        'api_key': secrets['TYPESENSE_API_KEY'],
        'connection_timeout_seconds': 2
    })
    return client

def element_to_typesense_doc(element: Dict[str, Any]) -> Dict[str, Any]:
    doc = {
        'id': element['id'],
        'type': element['type'],
    }
    
    # document_id and document_title
    if 'document' in element and element['document']:
        doc['document_id'] = element['document'].get('id', '')
        doc['document_title'] = element['document'].get('title', '')
        
    # text and description
    if element.get('text'):
        doc['text'] = element['text']
    if element.get('description'):
        doc['description'] = element['description']
        
    # concept flattening
    concepts = element.get('concepts', [])
    concept_labels = []
    concept_categories = []
    concept_vocabularies = []
    concept_levels = []
    concept_tokens = []
    
    for concept in concepts:
        label = concept.get('label')
        category = concept.get('category')
        vocabulary = concept.get('vocabulary')
        pyramid_level = concept.get('pyramid_level')
        
        if label:
            concept_labels.append(label)
            concept_tokens.append(f"concept:{label}")
        if category:
            concept_categories.append(category)
            concept_tokens.append(f"category:{category}")
        if vocabulary:
            concept_vocabularies.append(vocabulary)
            concept_tokens.append(f"vocab:{vocabulary}")
        if pyramid_level is not None:
            concept_levels.append(pyramid_level)
            concept_tokens.append(f"level:{pyramid_level}")
            
    doc['concept_labels'] = concept_labels
    doc['concept_categories'] = concept_categories
    doc['concept_vocabularies'] = concept_vocabularies
    doc['concept_levels'] = concept_levels
    doc['concept_tokens'] = concept_tokens
    
    # metadata flattening
    metadata = element.get('metadata', [])
    metadata_names = []
    metadata_values = []
    for m in metadata:
        name = m.get('name')
        value = m.get('value')
        if name:
            metadata_names.append(name)
        if value is not None:
            metadata_values.append(str(value))
            
    doc['metadata_names'] = list(set(metadata_names))
    doc['metadata_values'] = list(set(metadata_values))
    
    return doc

def main():
    client = get_typesense_client()
    
    schema = {
        'name': 'elements',
        'fields': [
            {'name': 'id', 'type': 'string'},
            {'name': 'type', 'type': 'string', 'facet': True},
            {'name': 'document_id', 'type': 'string', 'optional': True},
            {'name': 'document_title', 'type': 'string', 'optional': True},
            {'name': 'text', 'type': 'string', 'optional': True},
            {'name': 'description', 'type': 'string', 'optional': True},
            {'name': 'concept_labels', 'type': 'string[]', 'optional': True},
            {'name': 'concept_categories', 'type': 'string[]', 'facet': True, 'optional': True},
            {'name': 'concept_vocabularies', 'type': 'string[]', 'facet': True, 'optional': True},
            {'name': 'concept_levels', 'type': 'int32[]', 'facet': True, 'optional': True},
            {'name': 'concept_tokens', 'type': 'string[]', 'optional': True},
            {'name': 'metadata_names', 'type': 'string[]', 'optional': True},
            {'name': 'metadata_values', 'type': 'string[]', 'optional': True}
        ]
    }
    
    print("Checking if collection exists...")
    try:
        client.collections['elements'].retrieve()
        print("Collection 'elements' exists. deleting it...")
        client.collections['elements'].delete()
    except Exception as e:
        pass
        
    client.collections.create(schema)
    print("Collection 'elements' created.")
    
    print("Loading data_objects_enriched.json...")
    with open("data_objects_enriched.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        
    elements = data.get('elements', [])
    docs = [element_to_typesense_doc(el) for el in elements]
    
    print(f"Indexing {len(docs)} documents...")
    
    batch_size = 200
    for i in range(0, len(docs), batch_size):
        batch = docs[i:i + batch_size]
        client.collections['elements'].documents.import_(batch, {'action': 'upsert'})
        print(f"Indexed batch {i//batch_size + 1}...")
        
    print("Indexing complete!")

if __name__ == '__main__':
    main()
