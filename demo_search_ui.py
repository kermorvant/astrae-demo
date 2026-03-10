import streamlit as st
import json
import re
from datetime import datetime
from dataclasses import dataclass
from typing import List

@dataclass
class SearchElement:
    id: str
    type: str
    text: str
    url: str
    context_id: str
    context_url: str
    metadata: List[dict] = None

@st.cache_data
def load_data(filepath: str) -> List[SearchElement]:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return [SearchElement(**item) for item in data]
    except FileNotFoundError:
        st.error(f"File {filepath} not found.")
        return []

def main():
    st.set_page_config(page_title="Data Search Demo", layout="wide")
    
    # Load data
    elements = load_data('data.json')
    if not elements:
        return
        
    # Sidebar filters
    st.sidebar.header("Search Filters")
    search_query = st.sidebar.text_input("Search text (case-insensitive):", "")
    type_options = list(set(e.type for e in elements))
    selected_types = st.sidebar.multiselect("Filter by type:", options=type_options, default=type_options)
    
    # Use Streamlit session state for pagination
    if 'page_num' not in st.session_state:
        st.session_state.page_num = 0

    # Find available numeric and date metadata keys ranges/min-max across the dataset
    numeric_meta = {}
    date_meta = {}
    
    for e in elements:
        if e.metadata:
            for m in e.metadata:
                m_name = m.get('name')
                m_val = m.get('value')
                m_type = m.get('type')
                
                if m_type == 'numeric' and m_val is not None:
                    try:
                        val = float(m_val)
                        if m_name not in numeric_meta:
                            numeric_meta[m_name] = {'min': val, 'max': val}
                        else:
                            numeric_meta[m_name]['min'] = min(numeric_meta[m_name]['min'], val)
                            numeric_meta[m_name]['max'] = max(numeric_meta[m_name]['max'], val)
                    except ValueError:
                        pass
                        
                elif m_type == 'date' and m_val is not None:
                    # Expecting YYYY-MM-DD
                    try:
                        # try to parse as date if it's a string
                        val = datetime.strptime(str(m_val).split('T')[0], '%Y-%m-%d').date()
                        if m_name not in date_meta:
                            date_meta[m_name] = {'min': val, 'max': val}
                        else:
                            date_meta[m_name]['min'] = min(date_meta[m_name]['min'], val)
                            date_meta[m_name]['max'] = max(date_meta[m_name]['max'], val)
                    except ValueError:
                        pass
    
    # Render Metadata Filters
    st.sidebar.markdown("---")
    st.sidebar.header("Metadata Filters")
    
    active_filters = {'numeric': {}, 'date': {}}
    
    for name, bounds in numeric_meta.items():
        if bounds['min'] < bounds['max']: # only show slider if there is a range
            # Use columns or expander to keep sidebar tidy
            with st.sidebar.expander(f"Filter by {name}"):
                selected_range = st.slider(
                    f"{name}", 
                    min_value=float(bounds['min']), 
                    max_value=float(bounds['max']), 
                    value=(float(bounds['min']), float(bounds['max'])),
                    key=f"slider_{name}"
                )
                if selected_range != (bounds['min'], bounds['max']):
                    active_filters['numeric'][name] = selected_range

    for name, bounds in date_meta.items():
        if bounds['min'] < bounds['max']:
            with st.sidebar.expander(f"Filter by {name}"):
                start_date = st.date_input(f"{name} (Start)", value=bounds['min'], min_value=bounds['min'], max_value=bounds['max'], key=f"ds_{name}")
                end_date = st.date_input(f"{name} (End)", value=bounds['max'], min_value=bounds['min'], max_value=bounds['max'], key=f"de_{name}")
                if start_date > bounds['min'] or end_date < bounds['max']:
                    active_filters['date'][name] = (start_date, end_date)

    # Reset page on new search or filter change
    current_state = (search_query, selected_types, list(active_filters['numeric'].items()), list(active_filters['date'].items()))
    if 'last_query' not in st.session_state or st.session_state.last_query != current_state:
        st.session_state.page_num = 0
        st.session_state.last_query = current_state

    # Filter data
    # We still allow filtering even if search text is empty
    results = elements
    
    if selected_types:
        results = [e for e in results if e.type in selected_types]
        
    if search_query:
        query_lower = search_query.lower()
        new_results = []
        for e in results:
            match_text = query_lower in (e.text or "").lower()
            match_meta = False
            
            if e.metadata:
                for m in e.metadata:
                    if m.get('type') == 'text' and m.get('value'):
                        if query_lower in str(m['value']).lower():
                            match_meta = True
                            break
            
            if match_text or match_meta:
                # We can store match properties dynamically on the object for rendering
                e._match_text = match_text
                e._match_meta = match_meta
                new_results.append(e)
        results = new_results
    # Apply metadata filters
    if active_filters['numeric'] or active_filters['date']:
        filtered_results = []
        for e in results:
            keep = True
            if not e.metadata:
                keep = False
            else:
                meta_dict = {m['name']: m for m in e.metadata}
                
                # Check numeric filters
                for name, (min_v, max_v) in active_filters['numeric'].items():
                    if name not in meta_dict:
                        keep = False
                        break
                    try:
                        val = float(meta_dict[name]['value'])
                        if not (min_v <= val <= max_v):
                            keep = False
                            break
                    except (ValueError, TypeError):
                        keep = False
                        break
                
                if not keep:
                    continue
                    
                # Check date filters
                for name, (start_d, end_d) in active_filters['date'].items():
                    if name not in meta_dict:
                        keep = False
                        break
                    try:
                        val = datetime.strptime(str(meta_dict[name]['value']).split('T')[0], '%Y-%m-%d').date()
                        if not (start_d <= val <= end_d):
                            keep = False
                            break
                    except (ValueError, TypeError):
                        keep = False
                        break
            
            if keep:
                filtered_results.append(e)
        results = filtered_results
        
    total_results = len(results)
    
    # Pagination logic
    items_per_page = 50
    start_idx = st.session_state.page_num * items_per_page
    end_idx = start_idx + items_per_page
    paginated_results = results[start_idx:end_idx]
        
    if total_results > 0:
        st.subheader(f"Found {total_results} results (showing {start_idx + 1}-{min(end_idx, total_results)})")
    else:
        st.subheader(f"Found 0 results")
    
    # Display results
    num_columns = 5
    for i in range(0, len(paginated_results), num_columns):
        cols = st.columns(num_columns)
        for j, col in enumerate(cols):
            if i + j < len(paginated_results):
                e = paginated_results[i + j]
                with col:
                    with st.container(border=True):
                        # Type tag and small link icon (no ID)
                        type_color = "#1f77b4" if e.type == "paragraph" else "#ff7f0e" if e.type == "illustration" else "#2ca02c"
                        st.markdown(f"<span style='background-color: {type_color}; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.8em;'>{e.type.upper()}</span> <a href='https://arkindex.teklia.com/element/{e.id}' target='_blank' style='text-decoration:none; font-size: 0.8em;'>🔗</a>", unsafe_allow_html=True)
                        
                        has_search = bool(search_query.strip())
                        match_text = getattr(e, '_match_text', False)
                        match_meta = getattr(e, '_match_meta', False)
                        
                        if e.type in ['illustration', 'painting']:
                            match_labels = []
                            if has_search:
                                if match_text:
                                    match_labels.append("content")
                                if match_meta:
                                    match_labels.append("metadata")
                            else:
                                match_labels.append("content")
                                
                            if not match_labels:
                                match_labels.append("content")
                                
                            st.markdown(f"**Matching : {', '.join(match_labels)}**")
                        else:
                            match_labels = []
                            if has_search:
                                if match_text:
                                    match_labels.append("text")
                                if match_meta:
                                    match_labels.append("metadata")
                            else:
                                match_labels.append("text")
                                
                            if not match_labels:
                                match_labels.append("text")
                            
                            st.markdown(f"**Matching : {', '.join(match_labels)}**")
                                
                            highlighted_text = e.text
                            if has_search and match_text:
                                # Truncate text around the search query
                                match = re.search(re.escape(search_query.strip()), e.text, re.IGNORECASE)
                                if match:
                                    start_idx = match.start()
                                    end_idx = match.end()
                                    
                                    prefix = e.text[:start_idx]
                                    suffix = e.text[end_idx:]
                                    
                                    prefix_words = prefix.split()
                                    suffix_words = suffix.split()
                                    
                                    truncated_prefix = " ".join(prefix_words[-10:]) if len(prefix_words) > 10 else prefix
                                    truncated_suffix = " ".join(suffix_words[:10]) if len(suffix_words) > 10 else suffix
                                    
                                    if len(prefix_words) > 10:
                                        truncated_prefix = "... " + truncated_prefix
                                    if len(suffix_words) > 10:
                                        truncated_suffix = truncated_suffix + " ..."
                                        
                                    highlighted_text = truncated_prefix + e.text[start_idx:end_idx] + truncated_suffix

                                # Add highlight markup
                                escaped_query = re.escape(search_query.strip())
                                highlighted_text = re.sub(
                                    f"({escaped_query})",
                                    r"<mark style='background-color: #ffeb3b; color: #000; padding: 0 4px; border-radius: 3px;'>\1</mark>",
                                    highlighted_text,
                                    flags=re.IGNORECASE
                                )
                                
                            st.markdown(f"{highlighted_text}", unsafe_allow_html=True)
                        
                        st.markdown(f"[![Snippet Image]({e.url})]({e.url})")
                        
                        with st.popover("Context"):
                            st.markdown(f"*Context* <a href='https://arkindex.teklia.com/element/{e.context_id}' target='_blank' style='text-decoration:none; font-size: 0.8em;'>🔗</a>", unsafe_allow_html=True)
                            st.markdown(f"[![Context Image]({e.context_url})]({e.context_url})")

    # Pagination controls at bottom
    if total_results > items_per_page:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            if st.button("Previous Page", disabled=(st.session_state.page_num == 0)):
                st.session_state.page_num -= 1
                st.rerun()
        with col3:
            if st.button("Next Page", disabled=(end_idx >= total_results)):
                st.session_state.page_num += 1
                st.rerun()

if __name__ == "__main__":
    main()
