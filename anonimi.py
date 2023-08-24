#!/usr/bin/env python3
import argparse
import json
import os
import re
import random
import sys
from operator import itemgetter
from string import ascii_lowercase, digits
from lxml import etree
from unidecode import unidecode


def parse_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "xml_file",
        type=str,
        help="XML file to be modified",
    )
    parser.add_argument(
        "--db",
        "-d",
        default='person.json',
        type=str,
        help="JSON file with person names",
    )
    parser.add_argument(
        "--force",
        "-f",
        action='store_true',
        help="Force changes even if the attribute exists in the XML file",
    )
    parser.add_argument(
        "--debug",
        "-D",
        action='store_true',
        help="Debug mode on",
    )

    return parser.parse_args()


def get_random_item(text):
    def repl(match):
        if re.search(r'^[0-9]+$', match.group(0)):
            return ''.join(random.choices(digits, k=len(match.group(0))))
        return ''.join(
            random.choices(ascii_lowercase, k=len(match.group(0))))

    if '@' in text:
        return re.sub(r'^[^@]+', repl, text)
    elif '.' in text:
        return re.sub(r'[^\.]{4,}', repl, text)
    return re.sub(r'([0-9]+)', repl, text)


def read_data(ifile):
    masc = []
    fem = []
    surname = []

    with open(ifile) as fi:
        for line in fi:
            name, nountype, freq = line.strip().split(',')
            if nountype == 'masc':
                masc.append((name, int(freq)))
            elif nountype == 'fem':
                fem.append((name, int(freq)))
            elif nountype == 'surname':
                surname.append((name, int(freq)))
            else:
                print(f"Invalid data type: {nountype}", file=sys.stderr)
                sys.exit(1)

    return {
        "fem": [n[0] for n in sorted(fem, key=itemgetter(1), reverse=True)],
        "masc": [n[0] for n in sorted(masc, key=itemgetter(1), reverse=True)],
        "surname": [
            n[0] for n in sorted(surname, key=itemgetter(1), reverse=True)
        ]
    }, {
        "normalized": {
            "fem": [
                normalize(n[0]) for n in sorted(
                    fem, key=itemgetter(1), reverse=True)
            ],
            "masc": [
                normalize(n[0]) for n in sorted(
                    masc, key=itemgetter(1), reverse=True)
            ],
            "surname": [
                normalize(n[0]) for n in sorted(
                    surname, key=itemgetter(1), reverse=True)
            ]
        },
        "original": {
            "fem": [n[0] for n in sorted(
                fem, key=itemgetter(1), reverse=True)],
            "masc": [n[0] for n in sorted(
                masc, key=itemgetter(1), reverse=True)],
            "surname": [
                n[0] for n in sorted(surname, key=itemgetter(1), reverse=True)
            ]
        }
    }


def get_info_from_file(xmlfile):
    return xmlfile.split('_')[1], xmlfile.split('_')[3]


def normalize(string):
    return unidecode(string)


def fix(string):
    if string.isupper() or string.islower():
        return string.title()
    return string


args = parse_args()

# read skels from json
with open(args.db, 'r') as f:
    skels = json.load(f)

tree = etree.parse(args.xml_file)
metadata = tree.find('metadata')

country, fid = get_info_from_file(
    metadata.xpath('.//source/text/file')[0].attrib['name'])

random.seed(fid)

if country == 'PT':
    orig_data, data = read_data("data/pt_data.csv")
elif country == 'BR':
    orig_data, data = read_data("data/br_data.csv")
elif country == 'ES':
    orig_data, data = read_data("data/es_data.csv")
elif country == 'GZ':
    orig_data, data = read_data("data/gz_data.csv")

if args.debug:
    print('DEBUG: Loaded {} names'.format(
        len(orig_data['fem']) +
        len(orig_data['masc']) +
        len(orig_data['surname'])))
    print(f"DEBUG: Using {country} for country", file=sys.stderr)
    print(f"DEBUG: Using {fid} as seed", file=sys.stderr)

# exceptions
exceptions = ["Marias", "Anas", "Argolos"]

root = tree.find('data')
store = {}
for node in root.xpath('.//entity[@type = "person"]'):
    if any(x in node.attrib for x in ['skip-anonym', 'wikidata']):
        if args.debug:
            print("DEBUG: skip {}".format(node.text))
        continue

    if 'anonymized' in node.attrib and args.force is False:
        continue

    if 'norm' in node.attrib:
        node.attrib.pop('norm')

    if node.text not in skels:
        print(f"Error: {node.text} not in person.json")
        sys.exit(1)
    skel = skels[node.text]
    anonymized = []
    for item, ntype in skel.items():
        new = ""
        init = 0
        end = 150
        norm = normalize(item)

        if norm in store:
            new = store[norm]
        else:
            if norm in data["normalized"][ntype]:
                init = data["normalized"][ntype].index(norm) + 1
                end = init + 20
            rnd = random.randint(init, end)
            if args.debug:
                print(f"DEBUG: got random {rnd} between {init} and {end}")
            new = orig_data[ntype][rnd]
            orig_data[ntype].pop(rnd)
            store[norm] = new

        if node.text in exceptions:
            new += 's'
        anonymized.append(new)
        node.attrib['anonymized'] = " ".join(anonymized)

for node in root.xpath(
        './/entity[@type = "email" or @type = "phone" or @type = "webpage"]'):
    if 'anonymized' in node.attrib and args.force is False:
        continue

    if 'norm' in node.attrib:
        node.attrib.pop('norm')
    node.attrib['anonymized'] = get_random_item(node.text)


_, inputfile = os.path.split(args.xml_file)
tree.write(
    "output-" + inputfile,
    xml_declaration=True,
    encoding='utf-8',
    method="xml")
