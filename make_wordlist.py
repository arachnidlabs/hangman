import argparse
import csv
import gzip
import heapq
import itertools
import logging
import re


logging.basicConfig(level=logging.DEBUG)


parser = argparse.ArgumentParser(description="Creates dictionaries from Google books 1-gram corpus")
parser.add_argument('--minyear', type=int, default=None, help="Earliest year to count frequency for")
parser.add_argument('--maxyear', type=int, default=None, help="Latest year to count frequency for")
parser.add_argument('--pos', action='append', default=[], help="Parts of speech to include")
parser.add_argument('--min_popularity', type=int, default=None, help="Minimum popularity to consider for inclusion")
parser.add_argument('--count', type=int, default=None, help="Maximum number of words to output")
parser.add_argument('--show_counts', action='store_true', default=False, help="Include counts in the output")
parser.add_argument('--minlength', type=int, default=None, help="Minimum word length")
parser.add_argument('--maxlength', type=int, default=None, help="Maximum word length")
parser.add_argument('--accept_re', type=str, default='', help="Include only words matching this regex")
parser.add_argument('--normalise', action='store_true', default=False, help="Normalise (trim and lowercase) words")
parser.add_argument('files', nargs='+', help="Files to process")


def read_file(filename):
  logging.info("Opening %s...", filename)
  if filename.endswith('.gz'):
    f = gzip.open(filename, 'r')
  else:
    f = open(filename, 'r')
  return csv.reader(f, delimiter='\t')


def read_dataset(files):
  return itertools.chain.from_iterable(read_file(filename) for filename in files)


def sum_counts(counts, minyear, maxyear):
  total = 0
  for word, year, times, volumes in counts:
    year = int(year)
    if (not minyear or year >= minyear) and (not maxyear or year <= maxyear):
      total += int(times)
  return total


def get_words(files, minyear, maxyear, pos):
  reader = read_dataset(files)
  reader = itertools.groupby(reader, lambda row: row[0])
  for i, (word, counts) in enumerate(reader):
    if i % 100000 == 0:
      logging.debug("Processed %d words.", i)
    word, _, part = word.partition('_')
    if pos and part not in pos:
      continue
    total = sum_counts(counts, minyear, maxyear)
    if total > 0:
      yield total, word


def filter_by_count(words, min_popularity):
  return ((count, word) for count, word in words if count >= min_popularity)


def filter_by_length(words, min_length, max_length):
  return (
    (count, word) for count, word in words
    if (not min_length or len(word) >= min_length) and (not max_length or len(word) <= max_length))


def filter_by_re(words, accept):
  acceptor = re.compile(accept)
  return ((count, word) for count, word in words if acceptor.match(word))


def most_popular(words, n):
  heap = []
  for word in words:
    if len(heap) < n:
      heapq.heappush(heap, word)
    elif word > heap[0]:
      heapq.heappushpop(heap, word)
  heap.sort(reverse=True)
  return heap


def normalise_words(words):
  for count, word in words:
    yield (count, word.strip().lower())


def main(args):
  words = get_words(args.files, args.minyear, args.maxyear, set(args.pos))
  if args.min_popularity:
    words = filter_by_count(words, args.min_popularity)
  if args.minlength or args.maxlength:
    words = filter_by_length(words, args.minlength, args.maxlength)
  if args.accept_re:
    words = filter_by_re(words, args.accept_re)
  if args.normalise:
    words = normalise_words(words)
  if args.count:
    words = most_popular(words, args.count)
  if args.show_counts:
    for count, word in words:
      print '%s\t%d' % (word, count)
  else:
    for count, word in words:
      print word


if __name__ == '__main__':
  main(parser.parse_args())
