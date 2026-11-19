"""Local source-capture and citation checks; semantic review remains independent.

These helpers never retrieve a source, authenticate connector evidence, follow a
link, or certify that a claim follows from an excerpt. Captures are untrusted data.
"""
from datetime import datetime
import hashlib
import html
import re
from urllib.parse import quote, urlsplit

from .contracts import ErrorDetail, ValidationError, canonical_json

SECTIONS = ('Summary', 'Decisions', 'Action items', 'Open questions')
TOOLS = {
    'outlook': {
        'mcp__codex_apps__microsoft_outlook_email_fetch_message',
        'mcp__codex_apps__microsoft_outlook_email_fetch_messages_batch',
        'mcp__codex_apps__microsoft_outlook_email_search_messages',
        'mcp__codex_apps__microsoft_outlook_email_list_messages',
    },
    'slack': {
        'mcp__codex_apps__slack_slack_read_thread',
        'mcp__codex_apps__slack_slack_read_channel',
        'mcp__codex_apps__slack_slack_search_public_and_private',
        'mcp__codex_apps__slack_slack_search_public',
    },
}


def _require(condition, code='invalid_brief'):
    if not condition:
        raise ValidationError([ErrorDetail(code, '$', 'Source or brief contract rejected')])


def _object(value, keys):
    _require(type(value) is dict and set(value) == set(keys))


def _text(value):
    _require(type(value) is str and bool(value.strip()))
    # Validate Unicode using the shared wire contract, without interpreting text.
    canonical_json(value)


def _id(value):
    _require(type(value) is str and re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', value) is not None)


def _stamp(value):
    _text(value)
    _require(re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})', value) is not None)
    if value[-1] != 'Z':
        _require(int(value[-5:-3]) < 24 and int(value[-2:]) < 60)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        _require(parsed.tzinfo is not None)
    except ValueError:
        _require(False)


def _identity(record):
    _require(type(record) is dict)
    _require(type(record.get('provider')) is str and record['provider'] in TOOLS)
    _text(record.get('record_id'))
    return record['provider'], record['record_id']


def _url(value, provider):
    _text(value)
    _require(not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value))
    try:
        url = urlsplit(value)
        host = url.hostname or ''
        allowed = (host in {'outlook.office.com', 'outlook.office365.com', 'outlook.live.com'}
                   if provider == 'outlook' else host.endswith('.slack.com') and host != '.slack.com')
        _require(url.scheme == 'https' and allowed and url.username is None and url.password is None
                 and url.port in (None, 443) and bool(url.path) and '\\' not in value)
    except ValueError:
        _require(False)


def validate_sources(bundle):
    """Validate the exact partition of selected records, not connector authenticity."""
    _object(bundle, ('schema_version', 'selection_ref', 'selected', 'sources', 'unavailable'))
    _require(type(bundle['schema_version']) is int and bundle['schema_version'] == 1)
    _text(bundle['selection_ref'])
    for key in ('selected', 'sources', 'unavailable'):
        _require(type(bundle[key]) is list)
    _require(bool(bundle['selected']))
    selected = []
    for item in bundle['selected']:
        _object(item, ('provider', 'record_id'))
        selected.append(_identity(item))
    _require(len(selected) == len(set(selected)))
    captured, ids = [], []
    for item in bundle['sources']:
        _object(item, ('id', 'provider', 'record_id', 'url', 'retrieved_at', 'message_at',
                       'completeness', 'content', 'retrieval_tool', 'evidence_ref'))
        captured.append(_identity(item))
        _id(item['id']); ids.append(item['id'])
        _url(item['url'], item['provider'])
        _stamp(item['retrieved_at']); _stamp(item['message_at'])
        _require(type(item['completeness']) is str and item['completeness'] in ('full', 'partial'))
        _text(item['content'])
        _require(type(item['retrieval_tool']) is str and item['retrieval_tool'] in TOOLS[item['provider']])
        ref = item['evidence_ref']
        _text(ref)
        _require(not ref.startswith('/') and '\\' not in ref and ':' not in ref and '\x00' not in ref
                 and all(p not in ('', '.', '..') for p in ref.split('/')))
    _require(len(ids) == len(set(ids)))
    for item in bundle['unavailable']:
        _object(item, ('provider', 'record_id', 'reason'))
        captured.append(_identity(item)); _text(item['reason'])
    _require(len(captured) == len(set(captured)) and set(captured) == set(selected))
    return bundle


def source_digest(bundle):
    """Bind all normalized source fields including selection and coverage."""
    validate_sources(bundle)
    return hashlib.sha256(canonical_json(bundle)).hexdigest()


def _check(bundle, brief):
    digest = source_digest(bundle)
    _object(brief, ('schema_version', 'title', 'sources_sha256', 'claims'))
    _require(type(brief['schema_version']) is int and brief['schema_version'] == 1)
    _text(brief['title'])
    _require(brief['sources_sha256'] == digest, 'stale_sources')
    _require(type(brief['claims']) is list and bool(brief['claims']))
    sources = {s['id']: s for s in bundle['sources']}
    ids = []
    for claim in brief['claims']:
        _object(claim, ('id', 'section', 'kind', 'text', 'owner', 'due', 'citations'))
        _id(claim['id']); ids.append(claim['id'])
        _require(type(claim['section']) is str and claim['section'] in SECTIONS)
        _require(type(claim['kind']) is str and claim['kind'] in ('fact', 'proposal', 'conflict', 'unknown'))
        for key in ('text', 'owner', 'due'):
            _text(claim[key])
        _require(type(claim['citations']) is list)
        _require(bool(claim['citations']) or claim['kind'] == 'unknown', 'missing_citation')
        if claim['kind'] == 'unknown':
            _require(claim['owner'] == claim['due'] == 'Unspecified')
        seen = set()
        for citation in claim['citations']:
            _object(citation, ('source_id', 'excerpt'))
            _id(citation['source_id']); _text(citation['excerpt'])
            source = sources.get(citation['source_id'])
            _require(source is not None, 'unknown_source')
            _require(citation['excerpt'] in source['content'], 'unsupported_excerpt')
            pair = (citation['source_id'], citation['excerpt'])
            _require(pair not in seen); seen.add(pair)
    _require(len(ids) == len(set(ids)))
    return digest


def verify_brief(bundle, brief):
    """Return sanitized structural findings; a pass leaves semantic review pending."""
    try:
        digest = _check(bundle, brief)
    except ValidationError as error:
        return dict(passed=False, errors=sorted({e.code for e in error.errors}),
                    verification_scope='snapshot_and_citations', semantic_review_required=True)
    return dict(passed=True, errors=[], sources_sha256=digest,
                verification_scope='snapshot_and_citations', semantic_review_required=True)


def _markdown(value):
    value = html.escape(' '.join(value.split()), quote=True)
    return re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', value)


def render_brief(bundle, brief):
    """Render only validated captured data, never execute source instructions."""
    digest = _check(bundle, brief)
    sources = {s['id']: s for s in bundle['sources']}
    lines = ['# ' + _markdown(brief['title']), '',
             'Verification: snapshot and citations checked; independent semantic review required.', '',
             f"Coverage: {len(bundle['sources'])} captured; {len(bundle['unavailable'])} unavailable; "
             f"{sum(s['completeness'] == 'partial' for s in bundle['sources'])} partial.", '',
             'Scope: ' + _markdown(bundle['selection_ref']), '']
    source_map = []
    for section in SECTIONS:
        lines += ['## ' + section, '']
        claims = [c for c in brief['claims'] if c['section'] == section]
        if not claims:
            lines += ['No statements included for this section from the selected capture.', '']
        for claim in claims:
            links, citations = [], []
            for c in claim['citations']:
                source = sources[c['source_id']]
                # Quote URL delimiters rather than allowing them to escape Markdown.
                url = quote(source['url'], safe=':/?=&%#@+;,')
                links.append(f"[{source['id']}]({url})")
                citations.append({**c, 'url': source['url'], 'provider': source['provider'],
                                  'record_id': source['record_id'], 'completeness': source['completeness'],
                                  'retrieved_at': source['retrieved_at'], 'message_at': source['message_at'],
                                  'evidence_ref': source['evidence_ref']})
            line = f"- [{claim['id']}; {claim['kind']}] {_markdown(claim['text'])}"
            if section == 'Action items':
                line += f" Owner: {_markdown(claim['owner'])}; Due: {_markdown(claim['due'])}."
            lines += [line + (' ' + ' '.join(links) if links else ' (Source-bounded unknown; review required.)'), '']
            source_map.append(dict(claim_id=claim['id'], text=claim['text'], section=section,
                                   kind=claim['kind'], owner=claim['owner'], due=claim['due'], citations=citations))
    lines += ['Sources captured (message time; retrieval time; coverage):', '']
    for source in bundle['sources']:
        lines.append(f"- {source['id']}: {source['message_at']}; {source['retrieved_at']}; {source['completeness']}.")
    for item in bundle['unavailable']:
        lines.append(f"- Unavailable {_markdown(item['provider'])} record {_markdown(item['record_id'])}: {_markdown(item['reason'])}.")
    return dict(markdown='\n'.join(lines) + '\n', source_map=source_map,
                sources_sha256=digest, semantic_review_required=True)
