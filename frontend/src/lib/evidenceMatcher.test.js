import test from 'node:test'
import assert from 'node:assert/strict'
import {
  findQuotationOccurrences,
  splitTextWithHighlights,
} from './evidenceMatcher.js'

test('1. Exact matching locates verbatim quotations and preserves exact offsets', () => {
  const text = 'Project Apollo lunar module guidance computer had 36,864 words of ROM.'
  const quote = '36,864 words of ROM.'
  const matches = findQuotationOccurrences(text, quote)

  assert.equal(matches.length, 1)
  assert.equal(matches[0].matchType, 'exact')
  assert.equal(matches[0].text, quote)
  assert.equal(text.slice(matches[0].start, matches[0].end), quote)
})

test('2. Multiple identical quotations are all found and indexed deterministically', () => {
  const text = 'Telemetry rate is 51.2 kbps during launch. Telemetry rate is 51.2 kbps during orbital insertion.'
  const quote = 'Telemetry rate is 51.2 kbps'
  const matches = findQuotationOccurrences(text, quote)

  assert.equal(matches.length, 2)
  assert.equal(matches[0].matchIndex, 0)
  assert.equal(matches[1].matchIndex, 1)
  assert.equal(matches[0].text, quote)
  assert.equal(matches[1].text, quote)
  assert(matches[0].start < matches[1].start)
})

test('3. Curly and straight quotation marks match seamlessly', () => {
  const textWithCurly = 'The engineer stated: “Emergency abort mode 1A requires manual initiation.”'
  const quoteStraight = '"Emergency abort mode 1A requires manual initiation."'
  const matches = findQuotationOccurrences(textWithCurly, quoteStraight)

  assert.equal(matches.length, 1)
  assert.equal(matches[0].matchType, 'normalized')
  assert.equal(matches[0].text, '“Emergency abort mode 1A requires manual initiation.”')

  // Reverse direction: straight in text, curly in quote
  const textWithStraight = 'The command was "ABORT STAGE 1" immediately.'
  const quoteCurly = '“ABORT STAGE 1”'
  const matchesReverse = findQuotationOccurrences(textWithStraight, quoteCurly)
  assert.equal(matchesReverse.length, 1)
  assert.equal(matchesReverse[0].text, '"ABORT STAGE 1"')
})

test('4. Non-breaking spaces and irregular unicode whitespace are normalized', () => {
  const textWithNBSP = 'Downlink bandwidth was 100\u00A0MB per second across all channels.'
  const quoteWithSpace = '100 MB per second'
  const matches = findQuotationOccurrences(textWithNBSP, quoteWithSpace)

  assert.equal(matches.length, 1)
  assert.equal(matches[0].matchType, 'normalized')
  assert.equal(matches[0].text, '100\u00A0MB per second')
})

test('5. Multi-line whitespace and consecutive spaces collapse safely to original offsets', () => {
  const textWithNewlines = 'System specifications:\n\n   Downlink   bandwidth:   51.2 kbps.\n\nEnd of section.'
  const quoteSingleSpace = 'Downlink bandwidth: 51.2 kbps.'
  const matches = findQuotationOccurrences(textWithNewlines, quoteSingleSpace)

  assert.equal(matches.length, 1)
  assert.equal(matches[0].matchType, 'normalized')
  assert.equal(matches[0].text, 'Downlink   bandwidth:   51.2 kbps.')
})

test('6. Unicode text with accents and symbols is handled safely', () => {
  const text = 'L’atmosphère de Titan possède une concentration d’azote de 95% ± 2% à 20°C.'
  const quote = 'concentration d’azote de 95% ± 2% à 20°C.'
  const matches = findQuotationOccurrences(text, quote)

  assert.equal(matches.length, 1)
  assert.equal(matches[0].text, quote)
})

test('7. Special characters such as $, [], *, and () do not break regex or indexing', () => {
  const text = 'The total budget [estimated at $25.4 billion (FY1973)] was approved *unanimously*.'
  const quote = '[estimated at $25.4 billion (FY1973)] was approved *unanimously*'
  const matches = findQuotationOccurrences(text, quote)

  assert.equal(matches.length, 1)
  assert.equal(matches[0].matchType, 'exact')
  assert.equal(matches[0].text, quote)
})

test('8. Empty, whitespace-only, or missing inputs return empty array safely', () => {
  assert.deepEqual(findQuotationOccurrences('', 'quote'), [])
  assert.deepEqual(findQuotationOccurrences(null, 'quote'), [])
  assert.deepEqual(findQuotationOccurrences('text', ''), [])
  assert.deepEqual(findQuotationOccurrences('text', '   '), [])
  assert.deepEqual(findQuotationOccurrences('text', null), [])
})

test('9. Unmatched quotations report 0 matches without false or approximate highlighting', () => {
  const text = 'Apollo 11 landed on the Sea of Tranquility on July 20, 1969.'
  const nonExistentQuote = 'Apollo 11 landed in the Pacific Ocean on July 20, 1969.'
  const matches = findQuotationOccurrences(text, nonExistentQuote)

  assert.equal(matches.length, 0, 'Must never produce approximate or false matches')

  const split = splitTextWithHighlights(text, nonExistentQuote)
  assert.equal(split.totalMatches, 0)
  assert.equal(split.matchType, 'none')
  assert.equal(split.segments.length, 1)
  assert.equal(split.segments[0].isHighlight, false)
  assert.equal(split.segments[0].text, text)
})

test('10. splitTextWithHighlights segments text cleanly and designates active match', () => {
  const text = 'Alpha S1 Beta S1 Gamma'
  const quote = 'S1'
  const split = splitTextWithHighlights(text, quote, 1) // active match index 1

  assert.equal(split.totalMatches, 2)
  assert.equal(split.matchType, 'exact')

  // Segments: ['Alpha ', 'S1', ' Beta ', 'S1', ' Gamma']
  assert.equal(split.segments.length, 5)
  assert.equal(split.segments[0].text, 'Alpha ')
  assert.equal(split.segments[0].isHighlight, false)

  assert.equal(split.segments[1].text, 'S1')
  assert.equal(split.segments[1].isHighlight, true)
  assert.equal(split.segments[1].matchIndex, 0)
  assert.equal(split.segments[1].isActive, false)

  assert.equal(split.segments[2].text, ' Beta ')
  assert.equal(split.segments[2].isHighlight, false)

  assert.equal(split.segments[3].text, 'S1')
  assert.equal(split.segments[3].isHighlight, true)
  assert.equal(split.segments[3].matchIndex, 1)
  assert.equal(split.segments[3].isActive, true)

  assert.equal(split.segments[4].text, ' Gamma')
  assert.equal(split.segments[4].isHighlight, false)
})

test('11. Emoji and surrogate pairs are matched with accurate offsets in exact and normalized modes', () => {
  // Exact match with emoji
  const textEmoji = 'Orbital telemetry: 🛰️ active at apogee 🚀.'
  const quoteEmoji = '🛰️ active at apogee 🚀'
  const exactMatches = findQuotationOccurrences(textEmoji, quoteEmoji)
  assert.equal(exactMatches.length, 1)
  assert.equal(exactMatches[0].matchType, 'exact')
  assert.equal(textEmoji.slice(exactMatches[0].start, exactMatches[0].end), quoteEmoji)

  // Normalized match with emoji, curly quotes, and extra whitespace
  const textNormEmoji = 'Status update:\n\n   Satellite “🛰️” is   operational 🚀   today.'
  const quoteNormEmoji = 'Satellite "🛰️" is operational 🚀'
  const normMatches = findQuotationOccurrences(textNormEmoji, quoteNormEmoji)
  assert.equal(normMatches.length, 1)
  assert.equal(normMatches[0].matchType, 'normalized')
  assert.equal(
    textNormEmoji.slice(normMatches[0].start, normMatches[0].end),
    'Satellite “🛰️” is   operational 🚀'
  )
})

