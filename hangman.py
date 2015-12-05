from collections import defaultdict, namedtuple
import csv
import jinja2
import logging
import math
import os
import random


word_ranks = defaultdict(int)
for word, count in csv.reader(open('20knouns.txt'), delimiter='\t'):
    word_ranks[word.decode('utf-8').strip().lower()] += int(count)
words = [word for word, count in sorted(word_ranks.iteritems(), key=lambda (w,c): c, reverse=True)][:5000]
words_by_length = defaultdict(list)
for word in words:
    words_by_length[len(word)].append(word)
alphabet = set("abcdefghijklmnopqrstuvwxyz")


def make_pattern(word, ch):
    return u''.join(word[i] if word[i] == ch or word[i] < 'a' or word[i] > 'z' else u'_' for i in range(len(word)))

def combine_patterns(first, second):
    return u''.join(b if a == u'_' else a for a, b in zip(first, second))

def group_by_patterns(words, ch):
    groups = defaultdict(list)
    for word in words:
        groups[make_pattern(word, ch)].append(word)
    return groups


Node = namedtuple('Node', ['guess', 'value'])
Entry = namedtuple('Entry', ['pattern', 'is_leaf', 'value'])
Section = namedtuple('Section', ['id', 'pattern', 'wrong', 'guess', 'entries'])


def score_grouping(subgroups, pattern):
    return (
#        len(subgroups.get(pattern, ())),
        sum(word_ranks[word] for word in subgroups.get(pattern, ())),
        max(len(v) for v in subgroups.values())
    )

def build_graph(pattern, words, letters, wrong=0):
    if wrong == 6:
        return Node('', None), words
    elif len(words) == 1:
        return Node('', words[0]), []

    best_guess = None
    for ch in letters:
        subgroups = group_by_patterns(words, ch)
        guess = (
            score_grouping(subgroups, pattern),
            ch,
            subgroups)
        if not best_guess or guess < best_guess:
            best_guess = guess
    score, ch, subgroups = best_guess

    subnodes = {}
    total_pruned = []
    for subpattern, subwords in subgroups.iteritems():
        new_pattern = combine_patterns(pattern, subpattern)
        subnodes[new_pattern], pruned = build_graph(
            new_pattern,
            subwords,
            letters - set([ch]),
            wrong + 1 if new_pattern == pattern else wrong)
        total_pruned.extend(pruned)

    return Node(ch, subnodes), total_pruned


def build_complete_graph(words):
    graph = {}
    total_pruned = []
    for length, words in words_by_length.iteritems():
        pattern = u'_' * length
        graph[pattern], pruned = build_graph(pattern, words, alphabet)
        total_pruned.extend(pruned)
    return graph, total_pruned


def get_entry_value(graph, node_map, subnode_key):
    if not subnode_key:
        return True, None
    elif graph[subnode_key].guess == '':
        if not graph[subnode_key].value:
            # Player wins
            return True, None
        else:
            # We make a guess
            return True, graph[subnode_key].value[0]
    else:
        return False, node_map[subnode_key]


def produce_book_data(pattern, node, start_id=1, wrong=0):
    entries = []
    subsections = []
    for subpattern, subnode in sorted(node.value.iteritems()):
        if subnode.guess == '':
            entries.append(Entry(subpattern, True, subnode.value))
        else:
            subsection_id = start_id + len(subsections) + 1
            entries.append(Entry(subpattern, False, subsection_id))
            if pattern == subpattern:
                subsections.extend(produce_book_data(subpattern, subnode, subsection_id, wrong + 1))
            else:
                subsections.extend(produce_book_data(subpattern, subnode, subsection_id, wrong))
    return [Section(start_id, pattern, wrong, node.guess, entries)] + subsections


def produce_complete_book_data(graph):
    sections = []
    lengths = []
    for pattern, node in sorted(graph.iteritems()):
        section_id = len(sections) + 1
        lengths.append((len(pattern), section_id))
        sections.extend(produce_book_data(pattern, node, section_id))
    return sections, lengths


def book():
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(os.getcwd()))
    template = env.get_template("book.html")
    graph, pruned = build_complete_graph(words)
    if pruned:
        logging.warn("Pruned %d words due to too many wrong guesses: %r", len(pruned), pruned)
    sections, lengths = produce_complete_book_data(graph)
    print template.render({
        'lengths': lengths,
        'sections': sections,
    }).encode('utf-8')

def hangman():
    length = int(raw_input("Number of letters? "))
    template = u'_' * length
    guesses = 0

    while True:
        guess, new_templates = graph[guesses, template]
        new_templates = sorted(list(new_templates))
        if guess == '':
            print "I guess %s!" % (new_templates[0])
            return
        print "I guess '%s'" % (guess,)
        for i, new_template in enumerate(new_templates):
            print "%d) %s" % (i, new_template)
        idx = int(raw_input("> "))
        template = new_templates[idx]
        if '_' not in template:
            print "I win!"
            return
        guesses += 1


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    book()
