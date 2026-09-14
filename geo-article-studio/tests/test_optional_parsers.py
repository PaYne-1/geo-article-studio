"""Actual optional parsers, using generated fictional documents with extractable text."""
import pytest
from pathlib import Path

def test_real_docx_xlsx_pdf_text_extraction(tmp_path):
    docx=pytest.importorskip('docx');openpyxl=pytest.importorskip('openpyxl');pypdf=pytest.importorskip('pypdf')
    from geo_article_studio.libraries import LibraryIndex
    libraries={}
    for kind in ('chat','product_info','reference_images','product_images'):
        p=tmp_path/kind;p.mkdir();libraries[kind]=str(p)
    root=Path(libraries['product_info'])
    d=docx.Document();d.add_paragraph('Fictional DOCX transport evidence');d.save(root/'fictional.docx')
    w=openpyxl.Workbook();w.active.append(['Fictional XLSX transport evidence']);w.save(root/'fictional.xlsx')
    from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
    writer=pypdf.PdfWriter();page=writer.add_blank_page(width=300,height=100)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 10 50 Td (Fictional PDF transport evidence) Tj ET')
    page[NameObject('/Contents')]=writer._add_object(stream)
    with (root/'fictional.pdf').open('wb') as handle:writer.write(handle)
    index=LibraryIndex({'libraries':libraries,'workspace_root':str(tmp_path/'work'),'output_root':str(tmp_path/'out')})
    report=index.update();assert report['failed']==0
    for query in ('DOCX','XLSX','PDF'):
        rows=index.search(query,library_type='product_info')
        assert any(query in row['snippet'] for row in rows)
