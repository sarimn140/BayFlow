import {
  HELP_TOPICS,
  OFF_TOPIC_TEXT,
  STARTER_QUESTIONS,
  UNKNOWN_TEXT,
  WELCOME_TEXT,
  type HelpLink,
  type HelpTopic,
} from './knowledge'

/**
 * The Help agent's brain: a small, deterministic retrieval engine over `HELP_TOPICS`. It never
 * calls a model and never answers from anywhere else, so it can only say what the site's own
 * knowledge base says; anything unrelated to BayFlow gets a polite refusal.
 */

export interface HelpReply {
  kind: 'answer' | 'greeting' | 'thanks' | 'unknown' | 'off-topic'
  text: string
  links: ReadonlyArray<HelpLink>
  /** One-tap follow-up questions. */
  suggestions: ReadonlyArray<string>
  /** The topic answered, when `kind` is `answer`. */
  topicId?: string
}

const STOP_WORDS = new Set([
  'a',
  'an',
  'the',
  'is',
  'are',
  'was',
  'were',
  'be',
  'am',
  'do',
  'does',
  'did',
  'to',
  'of',
  'in',
  'on',
  'at',
  'for',
  'and',
  'or',
  'it',
  'its',
  'this',
  'that',
  'my',
  'me',
  'i',
  'you',
  'your',
  'can',
  'could',
  'would',
  'should',
  'will',
  'how',
  'what',
  'when',
  'why',
  'who',
  'which',
  'please',
  'tell',
  'about',
  'with',
  'if',
  'there',
  'any',
  'have',
  'has',
  'just',
  'want',
  'need',
  'so',
  'as',
  'by',
  'from',
  'up',
  'out',
  'then',
  'some',
  'us',
  'we',
  'our',
  'im',
  'ive',
  'hi',
  'hello',
  'hey',
  'right',
  'now',
  'currently',
  'still',
  'got',
  'more',
  'than',
  'one',
  'choose',
  'know',
  'make',
  'use',
  'difference',
  'between',
  'explain',
  'describe',
  'show',
  'give',
  'mean',
  'meaning',
])

/** Words folded together before matching ("mechanic" = "technician", "cost" = "price"). */
const SYNONYMS: Record<string, string> = {
  mechanic: 'technician',
  tech: 'technician',
  adviser: 'advisor',
  sa: 'advisor',
  cost: 'price',
  pricing: 'price',
  charge: 'price',
  fee: 'price',
  garage: 'shop',
  workshop: 'shop',
  store: 'shop',
  car: 'vehicle',
  tyre: 'tire',
  labor: 'labour',
  approval: 'approve',
  accept: 'approve',
  accepted: 'approve',
  decline: 'reject',
  login: 'signin',
  log: 'signin',
  sign: 'signin',
  signup: 'register',
  appointment: 'book',
  reserve: 'book',
  quality: 'qc',
  colour: 'color',
  night: 'dark',
  moon: 'dark',
  mobile: 'phone',
  smartphone: 'phone',
  receive: 'receiv',
  received: 'receiv',
  receiving: 'receiv',
  ready: 'ready',
  pick: 'pickup',
  collect: 'pickup',
  finished: 'complete',
  completed: 'complete',
  wheres: 'where',
  whats: 'what',
}

/** Words that mean "this is about the site" even when no topic matches well. */
const SITE_ANCHORS = new Set([
  'bayflow',
  'book',
  'shop',
  'repair',
  'estimate',
  'vehicle',
  'service',
  'technician',
  'advisor',
  'owner',
  'qc',
  'part',
  'inventory',
  'purchase',
  'customer',
  'signin',
  'register',
  'account',
  'notification',
  'pickup',
  'dashboard',
  'theme',
  'dark',
  'demo',
  'slot',
  'booking',
  'pos',
  'website',
  'password',
  'labour',
  'invoice',
  'admin',
  'workflow',
  'approve',
  'reject',
  'cancel',
  'track',
  'login',
  'order',
  'payment',
  'phon',
  'app',
  'support',
])

export function stem(word: string): string {
  let w = word
  if (w.length > 4 && w.endsWith('ies')) w = `${w.slice(0, -3)}y`
  else if (w.length > 5 && w.endsWith('ing')) w = w.slice(0, -3)
  else if (w.length > 4 && w.endsWith('ed')) w = w.slice(0, -2)
  else if (w.length > 3 && w.endsWith('s') && !w.endsWith('ss')) w = w.slice(0, -1)
  if (w.length > 4 && w.endsWith('e')) w = w.slice(0, -1)
  return w
}

/** Lower-case, strip punctuation, drop stop words, fold synonyms, trim endings. */
export function tokenize(text: string): string[] {
  const out: string[] = []
  const words = text
    .toLowerCase()
    .replace(/[’']/g, '')
    .split(/[^a-z0-9]+/)
  for (const raw of words) {
    if (!raw || STOP_WORDS.has(raw)) continue
    const folded = SYNONYMS[raw] ?? raw
    // Fold synonyms again after stemming, so "tyres" and "approved" land on one form.
    const stemmed = stem(folded)
    out.push(SYNONYMS[stemmed] ?? stemmed)
  }
  return out
}

interface IndexedTopic {
  topic: HelpTopic
  /** Every normalised word the topic is about, with how strongly each one points to it. */
  weights: ReadonlyMap<string, number>
  /** Multi-word keywords, kept whole: matching all their words is worth a bonus. */
  phrases: ReadonlyArray<ReadonlyArray<string>>
}

function buildIndex(topics: ReadonlyArray<HelpTopic>): ReadonlyArray<IndexedTopic> {
  return topics.map((topic) => {
    const weights = new Map<string, number>()
    const phrases: string[][] = []
    const raise = (token: string, value: number) => {
      if ((weights.get(token) ?? 0) < value) weights.set(token, value)
    }
    for (const keyword of topic.keywords) {
      const tokens = tokenize(keyword)
      if (tokens.length === 1) raise(tokens[0]!, 1)
      else if (tokens.length > 1) {
        phrases.push(tokens)
        for (const token of tokens) raise(token, 0.45)
      }
    }
    for (const token of tokenize(topic.title)) raise(token, 0.6)
    return { topic, weights, phrases }
  })
}

const INDEX = buildIndex(HELP_TOPICS)

/**
 * Rare words say more than common ones: "cancel" points to one topic, "booking" to a dozen. The
 * weight of a word is ln(1 + topics / topics-that-use-it), so it falls as a word gets common.
 */
const IDF: ReadonlyMap<string, number> = (() => {
  const docs = new Map<string, number>()
  for (const entry of INDEX)
    for (const token of entry.weights.keys()) docs.set(token, (docs.get(token) ?? 0) + 1)
  const idf = new Map<string, number>()
  // Floored, so a word every topic shares ("booking") still counts when it is all that was asked.
  for (const [token, count] of docs)
    idf.set(token, Math.max(1.9, Math.log(1 + INDEX.length / count)))
  return idf
})()

/** A topic must score at least this to be answered (see `scoreTopic`). */
const MIN_SCORE = 1.8
/** …and explain at least this share of the question's meaningful words, unless it scores big. */
const MIN_COVERAGE = 0.5
const STRONG_SCORE = 6

interface Scored {
  score: number
  matched: number
}

function scoreTopic(entry: IndexedTopic, query: ReadonlySet<string>): Scored {
  let score = 0
  let matched = 0
  for (const token of query) {
    const weight = entry.weights.get(token)
    if (weight === undefined) continue
    matched += 1
    score += weight * (IDF.get(token) ?? 1)
  }
  for (const phrase of entry.phrases) {
    if (phrase.every((token) => query.has(token))) score += 1.5 + 0.5 * phrase.length
  }
  return { score, matched }
}

const GREETING =
  /^\s*(hi|hello|hey|hiya|salam|assalam[\w\s-]*|good (morning|afternoon|evening)|yo)\b[\s!.?]*$/i
/** "What can you do?" and friends: every word is a stop word, so match them as a whole. */
const ABOUT_ME =
  /^\s*(please\s+)?(what can you (do|help( me)?( with)?)|who are you|what are you|how can you help( me)?|what do you do|what can i ask( you)?|help)\W*$/i
const THANKS = /^\s*(thanks?|thank you|thx|ty|shukriya|great|ok(ay)?|cool|got it)\b[\s!.?a-z]*$/i

function starters(): ReadonlyArray<string> {
  return STARTER_QUESTIONS.slice(0, 4)
}

/** Rank every topic for a question, best first (topics with no overlap are dropped). */
export function rankTopics(
  question: string,
): Array<{ topic: HelpTopic; score: number; coverage: number }> {
  const query = new Set(tokenize(question))
  return INDEX.map((entry) => {
    const { score, matched } = scoreTopic(entry, query)
    return { topic: entry.topic, score, coverage: query.size === 0 ? 0 : matched / query.size }
  })
    .filter((hit) => hit.score > 0)
    .sort((a, b) => b.score - a.score)
}

export function isGreeting(question: string): boolean {
  return GREETING.test(question)
}

/** Answer one question, only from the site's knowledge base. */
export function answerQuestion(question: string): HelpReply {
  const trimmed = question.trim()

  if (GREETING.test(trimmed)) {
    return { kind: 'greeting', text: WELCOME_TEXT, links: [], suggestions: starters() }
  }
  if (THANKS.test(trimmed)) {
    return {
      kind: 'thanks',
      text: 'You’re welcome! Ask me anything else about BayFlow whenever you like.',
      links: [],
      suggestions: starters(),
    }
  }

  if (ABOUT_ME.test(trimmed)) {
    const me = HELP_TOPICS.find((topic) => topic.id === 'help-agent')
    if (me) {
      return {
        kind: 'answer',
        text: me.answer,
        links: me.links ?? [],
        suggestions: me.followUps ?? starters(),
        topicId: me.id,
      }
    }
  }

  const ranked = rankTopics(trimmed)
  const best = ranked[0]
  const tokens = tokenize(trimmed)
  const aboutSite = tokens.some((token) => SITE_ANCHORS.has(token))

  // A lone generic word ("price of bitcoin") must not pull in a topic: unless the question names
  // something on the site, the topic has to explain most of what was asked.
  if (
    best &&
    best.score >= MIN_SCORE &&
    (best.coverage >= MIN_COVERAGE || best.score >= STRONG_SCORE) &&
    (aboutSite || best.coverage >= 0.75)
  ) {
    const own = best.topic.followUps ?? []
    const related = ranked
      .slice(1, 3)
      .filter((hit) => hit.score >= MIN_SCORE && hit.coverage >= MIN_COVERAGE)
      .map((hit) => hit.topic.title)
    const suggestions = [...own, ...related].filter((q, i, all) => all.indexOf(q) === i).slice(0, 3)
    return {
      kind: 'answer',
      text: best.topic.answer,
      links: best.topic.links ?? [],
      suggestions,
      topicId: best.topic.id,
    }
  }

  // Not a clear match: is it still about the site?
  if (aboutSite) {
    const nearest = ranked.slice(0, 3).map((hit) => hit.topic.title)
    return {
      kind: 'unknown',
      text: UNKNOWN_TEXT,
      links: [],
      suggestions: nearest.length > 0 ? nearest : starters(),
    }
  }

  return { kind: 'off-topic', text: OFF_TOPIC_TEXT, links: [], suggestions: starters() }
}
