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
words = [word for word, count in sorted(word_ranks.iteritems(), key=lambda (w,c): c, reverse=True)][:10000]
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


NodeKey = namedtuple('NodeKey', ['num_guesses', 'pattern'])
Node = namedtuple('Node', ['guess', 'wrong', 'patterns'])
Entry = namedtuple('Entry', ['pattern', 'is_leaf', 'value'])
Section = namedtuple('Section', ['id', 'pattern', 'wrong', 'guess', 'entries'])


def score_grouping(subgroups, pattern):
    return (
#        len(subgroups.get(pattern, ())),
        sum(word_ranks[word] for word in subgroups.get(pattern, ())),
        max(len(v) for v in subgroups.values())
    )


def build_graph(graph, pattern, words, letters, guesses=0, wrong=0):
    """Produces a graph of hangman guesses.

    graph is a dict of the form (num_guesses, pattern): (guess, wrong, patterns)
    Where:
      num_guesses: Is the total number of guesses so far
      pattern: Is the pattern of discovered letters so far (with underscores standing for unknown letters)unknown
      guess: Is the next character to guess
      wrong: The number of wrong guesses so far
      patterns: Is a list of patterns that can result from this guess with the given dictionary.

    The graph is constructed so as to minimise the size of the largest group of words with a single output
    pattern at each node in the tree.
    """
    if u'_' not in pattern:
        return []
    elif wrong == 6:
        # Pick one at random as our last guess
        graph[NodeKey(guesses, pattern)] = Node('', wrong, [])
        return words
    elif len(words) == 1:
        graph[NodeKey(guesses, pattern)] = Node('', wrong, words)
        return []
    # Find candidate guesses
    best_guess = None
    for ch in letters:
        subgroups = group_by_patterns(words, ch)
        guess = (
            score_grouping(subgroups, pattern),
            ch,
            subgroups)
        if not best_guess or guess < best_guess:
            best_guess = guess
    # Add the best guess to the graph and recurse
    score, ch, subgroups = best_guess
    graph[NodeKey(guesses, pattern)] = Node(ch, wrong, [combine_patterns(pattern, k) for k in subgroups.keys()])
    pruned = []
    for subpattern, subwords in subgroups.iteritems():
        new_pattern = combine_patterns(pattern, subpattern)
        pruned += build_graph(
            graph,
            new_pattern,
            subwords,
            letters - set([ch]),
            guesses + 1,
            (wrong + 1) if new_pattern == pattern else wrong)
    return pruned


def build_complete_graph(words):
    graph = {}
    pruned = []
    for length, words in words_by_length.iteritems():
        pruned += build_graph(graph, u'_' * length, words, alphabet)
    return graph, pruned


def get_entry_value(graph, node_map, subnode_key):
    if not subnode_key:
        return True, None
    elif graph[subnode_key].guess == '':
        if not graph[subnode_key].patterns:
            # Player wins
            return True, None
        else:
            # We make a guess
            return True, graph[subnode_key].patterns[0]
    else:
        return False, node_map[subnode_key]


def produce_book_data(graph):
    """Returns a structure designed for outputting the data in the book.

    The returned structure is a list, with one entry for each section in the final book.
    Each element in the list is a named tuple called Section, of this form:
      (id, pattern, wrong, guess, default, entries)
    Where:
      id: Is the number of this section
      pattern: Is the word thus far (eg, 'f_re__uck')
      wrong: The number of wrong guesses so far
      guess: Is this section's guessed letter. May be '' if this is a leaf section.
      entries: Is a list of entry tuples.

    An entry tuple has the following elements:
      (pattern, is_leaf, value)
    Where:
      pattern: Is the new part-guessed word for this entry
      is_leaf: Indicates if we think we've found the word
      value: Is a section number if leaf is False, and a guessed word if it is True.
    """
    # Filter out nodes that don't contain a guess (Eg, are leaf nodes) unless they're also the first guess
    nodes = [(k, v) for k, v in graph.items() if v.guess != '' or k.num_guesses == 0]
    # Start by shuffling the nodes randomly
    random.shuffle(nodes)
    # Then sort by number of guesses, so we always proceed forwards through the book
    nodes.sort(key=lambda (k, v): (k.num_guesses, len(k.pattern)))

    # Number the nodes
    nodes = list(enumerate(nodes, 1))

    # Construct a lookup table
    node_map = {k: idx for idx, (k, v) in nodes}

    # Generate the list of sections
    sections = []
    for idx, (k, v) in nodes:
        entries = []
        default_key = None
        for subpattern in v.patterns:
            subnode_key = NodeKey(k.num_guesses + 1, subpattern)
            if subpattern == k.pattern:
                entries.append(Entry(None, *get_entry_value(graph, node_map, subnode_key)))
            elif u'_' not in subpattern:
                entries.append(Entry(subpattern, True, (subpattern,)))
            else:
                entries.append(Entry(subpattern, *get_entry_value(graph, node_map, subnode_key)))
        entries.sort()
        sections.append(Section(idx, k.pattern, v.wrong, v.guess, entries))

    # Generate a map from length to initial section
    length_map = [(l, node_map[NodeKey(0, u'_'*l)]) for l in set(len(k.pattern) for k in graph.keys())]
    return sections, length_map

def book():
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(os.getcwd()))
    template = env.get_template("book.html")
    graph, pruned = build_complete_graph(words)
    if pruned:
        logging.warn("Pruned %d words due to too many wrong guesses: %r", len(pruned), pruned)
    sections, lengths = produce_book_data(graph)
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
