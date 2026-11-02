import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREFIX = 'experiments/window-family-v1/'
TAG = 'window-family-v1-registration'


def as_fraction(value):
    return Fraction(value['numerator'], value['denominator'])


def as_pair(value):
    return {'numerator': value.numerator, 'denominator': value.denominator}


def independent_windows(name, length):
    widths = {'document': [length], 'sliding': [4], 'dyadic': [2, 4, 8]}[name]
    intervals = []
    for width in widths:
        step = 1 if name == 'sliding' else width // 2 if name == 'dyadic' else width
        start = 0
        while start + width <= length:
            intervals.append((start, start + width))
            start += step
        last = (length - width, length)
        if last not in intervals:
            intervals.append(last)
    return intervals


def polynomial_tails(width):
    coefficients = [1]
    for _ in range(width):
        expanded = [0] * (len(coefficients) + 1)
        for k, coefficient in enumerate(coefficients):
            expanded[k] += 3 * coefficient
            expanded[k + 1] += coefficient
        coefficients = expanded
    return [Fraction(sum(coefficients[k:]), 4 ** width) for k in range(width + 1)]


def expected_row(sequence):
    if len(sequence) != 12 or set(sequence) - {'0', '1'}:
        raise ValueError('Invalid binary sequence')
    marks = sequence.count('1')
    weight = Fraction(3 ** (12 - marks), 4 ** 12)
    families = {}
    for name in ['document', 'sliding', 'dyadic']:
        spans = independent_windows(name, 12)
        minimum = Fraction(1)
        for left, right in spans:
            marked = sequence[left:right].count('1')
            minimum = min(minimum, polynomial_tails(right - left)[marked])
        families[name] = {'minimum_pvalue': as_pair(minimum),
                          'uncorrected': minimum <= Fraction(1, 20),
                          'bonferroni': minimum * len(spans) <= Fraction(1, 20)}
    return {'sequence': sequence, 'probability': as_pair(weight), 'families': families}


def check_row(row, sequence):
    expected = expected_row(sequence)
    if row != expected:
        raise ValueError('Sequence outcome differs: ' + sequence)
    return expected


def git_bytes(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def verify_history(provenance, fetch_history):
    commit = provenance['registration_commit']
    try:
        tagged = git_bytes('rev-parse', f'{TAG}^{{commit}}').decode().strip()
    except subprocess.CalledProcessError:
        if not fetch_history:
            raise ValueError('Registration tag unavailable. Use --fetch-history.')
        subprocess.run(['git', '-C', str(ROOT), 'fetch', '--no-tags', 'origin',
                        f'refs/tags/{TAG}:refs/tags/{TAG}'], check=True)
        tagged = git_bytes('rev-parse', f'{TAG}^{{commit}}').decode().strip()
    if tagged != commit:
        raise ValueError('Permanent tag and provenance disagree')
    registration_bytes = (HERE / 'registration.json').read_bytes()
    if git_bytes('show', f'{commit}:{PREFIX}registration.json') != registration_bytes:
        raise ValueError('Committed registration differs')
    if hashlib.sha256(registration_bytes).hexdigest() != provenance['registration_sha256']:
        raise ValueError('Registration hash differs')
    registration = json.loads(registration_bytes)
    for path, digest in registration['files'].items():
        data = (ROOT / path).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest or git_bytes('show', f'{commit}:{path}') != data:
            raise ValueError('Registered file differs: ' + path)
    base = registration['base_commit']
    subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', base, commit], check=True)


def verify_outputs(folder=HERE):
    provenance = json.loads((folder / 'provenance.json').read_text())
    for path, digest in provenance['outputs'].items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest:
            raise ValueError('Output hash differs: ' + path)
    cfg = json.loads((folder / 'config.json').read_text())
    report = json.loads((folder / 'run/report.json').read_text())
    if report['config'] != cfg or cfg['length'] != 12 or cfg['mark_probability'] != as_pair(Fraction(1, 4)):
        raise ValueError('Configuration differs')
    total = Fraction()
    totals = {name: {rule: [0, Fraction()] for rule in ['uncorrected', 'bonferroni']}
              for name in ['document', 'sliding', 'dyadic']}
    count = 0
    with (folder / 'run/outcomes.jsonl').open() as stream:
        for index, line in enumerate(stream):
            if index >= 4096:
                raise ValueError('Too many outcomes')
            sequence = format(index, '012b')
            row = check_row(json.loads(line), sequence)
            weight = as_fraction(row['probability'])
            total += weight
            count += 1
            for name in totals:
                for rule in totals[name]:
                    if row['families'][name][rule]:
                        totals[name][rule][0] += 1
                        totals[name][rule][1] += weight
    if count != 4096 or total != 1 or report['sequence_count'] != count or report['total_probability'] != as_pair(total):
        raise ValueError('Probability total or sequence count differs')
    if len(report['families']) != 3:
        raise ValueError('Family count differs')
    for saved, name in zip(report['families'], totals):
        spans = independent_windows(name, 12)
        expected = {'id': name, 'windows': [list(w) for w in spans], 'window_count': len(spans),
                    'thresholds': {'uncorrected': as_pair(Fraction(1, 20)),
                                   'bonferroni': as_pair(Fraction(1, 20 * len(spans)))},
                    'rules': {rule: {'rejecting_sequences': values[0],
                                    'family_false_positive_probability': as_pair(values[1]),
                                    'at_most_alpha': values[1] <= Fraction(1, 20)}
                              for rule, values in totals[name].items()}}
        if saved != expected:
            raise ValueError('Family summary differs: ' + name)
    return provenance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fetch-history', action='store_true')
    args = parser.parse_args()
    provenance = json.loads((HERE / 'provenance.json').read_text())
    verify_history(provenance, args.fetch_history)
    verify_outputs()
    print('Independent verifier checked 4096 exact sequence weights, all window decisions and every family summary.')


if __name__ == '__main__':
    main()
