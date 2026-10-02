"""Deterministic public Markdown -> text PDF, outlines and chunk/page mapping.

Raw PDF, extracted text and rendered QA pages stay outside the repository.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader
import pypdfium2 as pdfium


def compact(text):
    return re.sub(r'\s+', '', text)


def build(root):
    source = json.loads((root / 'public-input.json').read_text(encoding='utf8'))
    pdfmetrics.registerFont(TTFont('BenchCJK', 'C:/Windows/Fonts/msyh.ttc', subfontIndex=0))
    target = root / 'public-corpus.pdf'
    canvas = Canvas(str(target), pagesize=(595, 842), invariant=1)
    canvas.setTitle('Public CS-Notes benchmark corpus')
    page, y, previous = 1, 792, -1
    mapping, segments = [], []

    def newpage():
        nonlocal page, y
        canvas.showPage(); page += 1; y = 792
        canvas.setFont('BenchCJK', 8)

    canvas.setFont('BenchCJK', 8)
    for di, doc in enumerate(source['docs']):
        if di:
            newpage()
        canvas.bookmarkPage(f'doc-{di}')
        canvas.addOutlineEntry(doc['name'], f'doc-{di}', level=0, closed=False)
        previous = 0
        offset = 0
        text = doc['text'].replace('\r\n', '\n')
        for li, line in enumerate(text.splitlines(keepends=True)):
            content = line.rstrip('\r\n')
            if content and y < 45:
                newpage()
            heading = re.match(r'^(#{1,6})\s+(.+)', content)
            if heading:
                level = min(len(heading[1]), previous + 1)
                key = f'h-{di}-{li}'
                canvas.bookmarkPage(key)
                canvas.addOutlineEntry(heading[2], key, level=level, closed=False)
                previous = level
            rest, at = content, 0
            while rest:
                if y < 45:
                    newpage()
                width, count = 0, 0
                for char in rest:
                    cw = pdfmetrics.stringWidth(char, 'BenchCJK', 8)
                    if width + cw > 499 and count:
                        break
                    width += cw; count += 1
                part = rest[:count]
                # PDF literal text remains searchable; tabs expand only for drawing.
                canvas.drawString(48, y, part.replace('\t', ' '))
                segments.append({'doc': doc['name'], 'start': offset + at, 'end': offset + at + count, 'page': page})
                y -= 11
                at += count; rest = rest[count:]
            if not content:
                y -= 11
            offset += len(line)
        if y < 45:
            y = 45
    canvas.save()
    reader = PdfReader(target)
    extracted = ''.join(p.extract_text() or '' for p in reader.pages)
    want = compact(''.join(d['text'] for d in source['docs']).replace('\t', ' '))
    if compact(extracted) != want:
        raise RuntimeError('PDF extracted text differs from source; do not benchmark')
    for chunk in source['chunks']:
        pages = sorted({s['page'] for s in segments if s['doc'] == chunk['docName'] and s['end'] > chunk['start'] and s['start'] < chunk['start'] + len(chunk['text'])})
        if not pages:
            raise RuntimeError('chunk has no source pages')
        mapping.append({'id': chunk['id'], 'doc': chunk['docName'], 'pages': pages})
    (root / 'page-map.json').write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding='utf8')
    document = pdfium.PdfDocument(str(target))
    for index in sorted({0, len(document) // 2, len(document) - 1}):
        image = document[index].render(scale=1.3).to_pil()
        image.save(root / f'pdf-qa-{index+1}.png')
    result = {'corpusCommit': source['commit'], 'pdfSha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'pages': len(reader.pages), 'sourceDocs': len(source['docs']), 'chunkMappings': len(mapping), 'textExtraction': 'exact after whitespace normalization; tabs drawn as spaces', 'renderedQaPages': [1, len(document)//2+1, len(document)], 'containsPublicText': True}
    (root / 'pdf-validation.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--raw', required=True)
    args = parser.parse_args()
    build(Path(args.raw))
