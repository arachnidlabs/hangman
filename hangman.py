from collections import defaultdict, namedtuple
import csv
import jinja2
import logging
import math
import os
import random


word_ranks = defaultdict(int)
for word, count in csv.reader(open('50knouns.txt'), delimiter='\t'):
    word_ranks[word.decode('utf-8').strip().lower()] += int(count)
words = [word for word, count in sorted(word_ranks.iteritems(), key=lambda (w,c): c, reverse=True)]
alphabet = set("abcdefghijklmnopqrstuvwxyz")


def separate_by_length(words):
    words_by_length = defaultdict(list)
    for word in words:
        words_by_length[len(word)].append(word)
    return words_by_length


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

def empty_pattern(pattern):
    return u'_' * len(pattern)

def score_grouping(subgroups, pattern):
    wrong_words = subgroups.get(empty_pattern(pattern), ())
    return (
        len(wrong_words),                                               # Minimise number of wrong words
        sum(word_ranks[word] for word in wrong_words),                  # Avoid popular wrong words
        -len(subgroups),                                                # Maximise branching factor
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

    # This guess might end up not contributing anything,
    # if we end up pruning things away.
    if len(subnodes) == 1:
        return subnodes.values()[0], total_pruned

    # Due to pruning, occasionally you end up with a subtree
    # with only one usable word in it.  Lift it back up.
    if len(subnodes) == 2:
        (pattern1, node1), (pattern2, node2) = subnodes.items()
        if pattern1 == pattern and node1.value is None:
            return node2, total_pruned
        if pattern2 == pattern and node2.value is None:
            return node1, total_pruned

    return Node(ch, subnodes), total_pruned


def build_complete_graph(words):
    graph = {}
    total_pruned = []
    for length, words in separate_by_length(words).iteritems():
        pattern = u'_' * length
        graph[pattern], pruned = build_graph(pattern, words, alphabet)
        total_pruned.extend(pruned)
    return graph, total_pruned


def augment_graph(graph, words):
    """Adds any words to the graph that can be added without inserting new sections."""
    added = []
    for word in words:
        pattern = empty_pattern(word)
        node = graph[pattern]
        while node.guess != '':
            pattern = combine_patterns(pattern, make_pattern(word, node.guess))
            if pattern not in node.value:
                # We can add this word without creating a new section
                node.value[pattern] = Node('', word)
                added.append(word)
                break
            node = node.value[pattern]
    return added


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
    for subpattern, subnode in sorted(node.value.iteritems(), key=lambda (k, v): (k!=pattern, k)):
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


def book(count, extended_count):
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(os.getcwd()))
    template = env.get_template("book.html")
    graph, pruned = build_complete_graph(words[:count])
    if pruned:
        logging.warn("Pruned %d words due to too many wrong guesses: %r", len(pruned), pruned)
        logging.warn("Pruned words are worth: %s", sum(word_ranks[word] for word in pruned))
    added = augment_graph(graph, words[count:extended_count + count])
    if added:
        added.sort(key=lambda w:(len(w), w))
        logging.info("Added %d words to existing sections", len(added))
    sections, lengths = produce_complete_book_data(graph)
    logging.info("Created %d sections", len(sections))
    logging.info("lengths: %s", [(a, b, b*100.0/len(sections)) for (a,b) in lengths])
    bookdata = template.render({
        'lengths': lengths,
        'sections': sections,
    }).encode('utf-8')
    print bookdata

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    book(4000, 22500)
