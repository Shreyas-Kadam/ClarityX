/**
 * Evidence Quotation Matching and Text Highlighting Engine for ClarityX
 *
 * Implements strict, evidence-traceable quotation matching:
 * 1. Exact string matching (case-sensitive and verbatim).
 * 2. Normalization matching (whitespace collapsing, non-breaking spaces, curly-to-straight quotes).
 * 3. Never claims fuzzy or approximate matches as verified evidence.
 * 4. Preserves original text offsets accurately through index mapping.
 */

/**
 * Normalizes quotes and non-breaking spaces for comparison.
 *
 * @param {string} str
 * @returns {string}
 */
export function normalizeCharacterVariants(str) {
  if (!str) return ''
  return str
    .replace(/[\u201C\u201D\u201E\u201F\u00AB\u00BB]/g, '"') // Curly & typographic double quotes
    .replace(/[\u2018\u2019\u201A\u201B]/g, "'") // Curly & typographic single quotes
    .replace(/[\u00A0\u2000-\u200B\u202F\u205F\u3000]/g, ' ') // Non-breaking & unicode spaces
}

/**
 * Builds a normalized version of the text alongside an index mapping array
 * that maps each character in the normalized string back to its starting
 * offset in the original string.
 *
 * @param {string} text
 * @returns {{ norm: string, map: number[] }}
 */
export function createNormalizedIndexMap(text) {
  if (!text) return { norm: '', map: [] }

  const converted = normalizeCharacterVariants(text)
  let norm = ''
  const map = []
  let inWhitespace = false

  for (let i = 0; i < converted.length; i++) {
    const ch = converted[i]
    if (/\s/.test(ch)) {
      if (!inWhitespace) {
        norm += ' '
        map.push(i)
        inWhitespace = true
      }
    } else {
      inWhitespace = false
      norm += ch
      map.push(i)
    }
  }

  return { norm, map }
}

/**
 * Normalizes a quotation string: collapses whitespace and normalizes quote variants.
 *
 * @param {string} quotation
 * @returns {string}
 */
export function normalizeQuotation(quotation) {
  if (!quotation) return ''
  const converted = normalizeCharacterVariants(quotation)
  return converted.replace(/\s+/g, ' ').trim()
}

/**
 * Finds all occurrences of a quotation in source text.
 *
 * Priority order:
 * 1. Exact string matching.
 * 2. Whitespace and quotation-variant normalized matching (mapped to original offsets).
 *
 * @param {string} fullText - Complete original source text
 * @param {string} quotation - The citation quotation to locate
 * @returns {Array<{ start: number, end: number, text: string, matchType: 'exact'|'normalized', matchIndex: number }>}
 */
export function findQuotationOccurrences(fullText, quotation) {
  if (!fullText || typeof fullText !== 'string' || !quotation || typeof quotation !== 'string') {
    return []
  }

  const cleanQuote = quotation.trim()
  if (!cleanQuote) {
    return []
  }

  const matches = []

  // --- Step 1: Exact matching (using indexOf to avoid regex escaping issues) ---
  let searchIdx = 0
  while (searchIdx <= fullText.length - cleanQuote.length) {
    const foundIdx = fullText.indexOf(cleanQuote, searchIdx)
    if (foundIdx === -1) break

    matches.push({
      start: foundIdx,
      end: foundIdx + cleanQuote.length,
      text: fullText.slice(foundIdx, foundIdx + cleanQuote.length),
      matchType: 'exact',
      matchIndex: matches.length,
    })
    searchIdx = foundIdx + cleanQuote.length
  }

  if (matches.length > 0) {
    return matches
  }

  // --- Step 2: Normalized matching ---
  const normQuote = normalizeQuotation(cleanQuote)
  if (!normQuote) {
    return []
  }

  const { norm: normText, map } = createNormalizedIndexMap(fullText)
  if (!normText || map.length === 0) {
    return []
  }

  let normSearchIdx = 0
  while (normSearchIdx <= normText.length - normQuote.length) {
    const foundNormIdx = normText.indexOf(normQuote, normSearchIdx)
    if (foundNormIdx === -1) break

    const normEndIdx = foundNormIdx + normQuote.length
    const origStart = map[foundNormIdx]
    const origLastCharIdx = map[normEndIdx - 1]

    if (origStart !== undefined && origLastCharIdx !== undefined && origLastCharIdx >= origStart) {
      // Determine end offset in original text (covering surrogate pair if applicable)
      const lastChar = fullText.codePointAt(origLastCharIdx)
      const lastCharLength = lastChar > 0xffff ? 2 : 1
      const origEnd = origLastCharIdx + lastCharLength

      matches.push({
        start: origStart,
        end: origEnd,
        text: fullText.slice(origStart, origEnd),
        matchType: 'normalized',
        matchIndex: matches.length,
      })
    }

    normSearchIdx = normEndIdx
  }

  return matches
}

/**
 * Splits source text into segments for safe React rendering with highlights.
 *
 * @param {string} fullText - Full extracted source content
 * @param {string} quotation - Citation quotation to highlight
 * @param {number} [activeMatchIndex=0] - Which match index should be active/focused
 * @returns {{
 *   segments: Array<{ text: string, isHighlight: boolean, matchIndex?: number, isActive?: boolean, matchType?: string }>,
 *   totalMatches: number,
 *   matchType: 'exact'|'normalized'|'none'
 * }}
 */
export function splitTextWithHighlights(fullText, quotation, activeMatchIndex = 0) {
  if (!fullText || typeof fullText !== 'string') {
    return { segments: [], totalMatches: 0, matchType: 'none' }
  }

  if (!quotation || typeof quotation !== 'string' || !quotation.trim()) {
    return {
      segments: [{ text: fullText, isHighlight: false }],
      totalMatches: 0,
      matchType: 'none',
    }
  }

  const occurrences = findQuotationOccurrences(fullText, quotation)
  if (occurrences.length === 0) {
    return {
      segments: [{ text: fullText, isHighlight: false }],
      totalMatches: 0,
      matchType: 'none',
    }
  }

  const segments = []
  let cursor = 0

  for (let i = 0; i < occurrences.length; i++) {
    const occ = occurrences[i]
    if (occ.start > cursor) {
      segments.push({
        text: fullText.slice(cursor, occ.start),
        isHighlight: false,
      })
    }

    segments.push({
      text: fullText.slice(occ.start, occ.end),
      isHighlight: true,
      matchIndex: occ.matchIndex,
      isActive: occ.matchIndex === activeMatchIndex,
      matchType: occ.matchType,
    })

    cursor = occ.end
  }

  if (cursor < fullText.length) {
    segments.push({
      text: fullText.slice(cursor),
      isHighlight: false,
    })
  }

  return {
    segments,
    totalMatches: occurrences.length,
    matchType: occurrences[0].matchType,
  }
}

