import argparse
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREFIX = 'experiments/window-family-v1/'
TAG = 'window-family-v1-registration'
REGISTERED = ['PLAN.md', 'config.json', 'experiment.py', 'verify.py', 'test_experiment.py']


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def fraction(value):
    return Fraction(value['numerator'], value['denominator'])


def pair(value):
    return {'numerator': value.numerator, 'denominator': value.denominator}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def config():
    value = json.loads((HERE / 'config.json').read_text())
    if value['length'] != 12 or fraction(value['mark_probability']) != Fraction(1, 4):
        raise ValueError('This registration requires length 12 and mark probability 1/4')
    if fraction(value['alpha']) != Fraction(1, 20):
        raise ValueError('This registration requires alpha 1/20')
    return value


def windows(family, length):
    result = []
    for width in family['widths']:
        stride = family['stride']
        step = width if stride == 'width' else width // 2 if stride == 'half-width' else stride
        if width <= 0 or width > length or step <= 0:
            raise ValueError('Invalid window width or stride')
        starts = list(range(0, length - width + 1, step))
        if starts[-1] != length - width:
            starts.append(length - width)
        result.extend((start, start + width) for start in starts)
    return list(dict.fromkeys(result))


def binomial_tail(width, marked, probability):
    return sum((Fraction(math.comb(width, k)) * probability ** k * (1 - probability) ** (width - k)
                for k in range(marked, width + 1)), Fraction())


def sequence_result(bits, cfg, intervals=None, tails=None):
    probability = fraction(cfg['mark_probability'])
    alpha = fraction(cfg['alpha'])
    intervals = intervals or {f['id']: windows(f, len(bits)) for f in cfg['families']}
    tails = tails or {(w, k): binomial_tail(w, k, probability)
                     for w in {b - a for ws in intervals.values() for a, b in ws}
                     for k in range(w + 1)}
    marked = sum(bits)
    weight = probability ** marked * (1 - probability) ** (len(bits) - marked)
    families = {}
    for name, spans in intervals.items():
        minimum = min(tails[(end - start, sum(bits[start:end]))] for start, end in spans)
        families[name] = {'minimum_pvalue': pair(minimum), 'uncorrected': minimum <= alpha,
                          'bonferroni': minimum <= alpha / len(spans)}
    return {'sequence': ''.join(map(str, bits)), 'probability': pair(weight), 'families': families}


def calculate(cfg):
    intervals = {f['id']: windows(f, cfg['length']) for f in cfg['families']}
    p = fraction(cfg['mark_probability'])
    tails = {(w, k): binomial_tail(w, k, p)
             for w in {b - a for ws in intervals.values() for a, b in ws}
             for k in range(w + 1)}
    counts = {name: {rule: 0 for rule in cfg['corrections']} for name in intervals}
    masses = {name: {rule: Fraction() for rule in cfg['corrections']} for name in intervals}
    total = Fraction()
    lines = []
    for bits in itertools.product((0, 1), repeat=cfg['length']):
        row = sequence_result(bits, cfg, intervals, tails)
        lines.append(encoded(row))
        mass = fraction(row['probability'])
        total += mass
        for name in intervals:
            for rule in cfg['corrections']:
                if row['families'][name][rule]:
                    counts[name][rule] += 1
                    masses[name][rule] += mass
    if total != 1:
        raise ValueError('Sequence probabilities do not sum to one')
    alpha = fraction(cfg['alpha'])
    rows = []
    for name, spans in intervals.items():
        rows.append({'id': name, 'windows': [list(w) for w in spans], 'window_count': len(spans),
                     'thresholds': {'uncorrected': pair(alpha), 'bonferroni': pair(alpha / len(spans))},
                     'rules': {rule: {'rejecting_sequences': counts[name][rule],
                                      'family_false_positive_probability': pair(masses[name][rule]),
                                      'at_most_alpha': masses[name][rule] <= alpha}
                               for rule in cfg['corrections']}})
    report = {'schema': 'declawd.window-family-results/v1', 'sequence_count': len(lines),
              'total_probability': pair(total), 'config': cfg, 'families': rows,
              'scope': 'Exact finite independent null. No power, corpus or provider performance claim.'}
    return b''.join(lines), encoded(report)


def register():
    config()
    target = HERE / 'registration.json'
    if target.exists() or (HERE / 'run').exists():
        raise ValueError('Registration or results already exist')
    value = {'schema': 'declawd.window-family-registration/v1', 'registered_at': datetime.now(timezone.utc).isoformat(),
             'base_commit': git('rev-parse', 'HEAD'), 'permanent_tag': TAG,
             'files': {PREFIX + name: digest((HERE / name).read_bytes()) for name in REGISTERED}}
    target.write_bytes(encoded(value))


def check_registration(commit, require_ancestor=False):
    value = json.loads((HERE / 'registration.json').read_text())
    if require_ancestor:
        git('merge-base', '--is-ancestor', commit, 'HEAD')
    recorded = subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{commit}:{PREFIX}registration.json'])
    if recorded != (HERE / 'registration.json').read_bytes():
        raise ValueError('Registration differs from the committed registration')
    for path, expected in value['files'].items():
        current = (ROOT / path).read_bytes()
        saved = subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{commit}:{path}'])
        if digest(current) != expected or saved != current:
            raise ValueError('Registered file changed: ' + path)
    if git('rev-parse', f'{TAG}^{{commit}}') != commit:
        raise ValueError('Permanent tag differs from the registration commit')
    return value


def run(commit):
    check_registration(commit, require_ancestor=True)
    folder = HERE / 'run'
    if folder.exists():
        raise ValueError('Results already exist. Use verify to recompute.')
    outcomes, report = calculate(config())
    folder.mkdir()
    (folder / 'outcomes.jsonl').write_bytes(outcomes)
    (folder / 'report.json').write_bytes(report)
    provenance = {'schema': 'declawd.window-family-provenance/v1', 'registration_commit': commit,
                  'registration_tag': TAG, 'registration_sha256': digest((HERE / 'registration.json').read_bytes()),
                  'ran_at': datetime.now(timezone.utc).isoformat(), 'python': platform.python_version(),
                  'outputs': {PREFIX + 'run/outcomes.jsonl': digest(outcomes), PREFIX + 'run/report.json': digest(report)}}
    (HERE / 'provenance.json').write_bytes(encoded(provenance))
    print(report.decode().strip())


def verify():
    provenance = json.loads((HERE / 'provenance.json').read_text())
    check_registration(provenance['registration_commit'])
    if digest((HERE / 'registration.json').read_bytes()) != provenance['registration_sha256']:
        raise ValueError('Registration hash differs from provenance')
    outcomes, report = calculate(config())
    for name, expected in [('outcomes.jsonl', outcomes), ('report.json', report)]:
        path = HERE / 'run' / name
        if path.read_bytes() != expected or digest(expected) != provenance['outputs'][PREFIX + 'run/' + name]:
            raise ValueError('Output differs: ' + name)
    print('Registered runner verified every outcome and exact summary.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['register', 'run', 'verify'])
    parser.add_argument('--registration-commit')
    args = parser.parse_args()
    if args.command == 'register':
        register()
    elif args.command == 'run':
        if not args.registration_commit:
            parser.error('run requires --registration-commit')
        run(args.registration_commit)
    else:
        verify()


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
