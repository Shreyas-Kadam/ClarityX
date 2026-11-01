import test from 'node:test'
import assert from 'node:assert/strict'
import {
  MAX_SOURCES,
  validateWebsiteSource,
  validatePastedTextSource,
  validateDocumentSource,
  executeSessionInitialization,
} from './newResearchWorkflow.js'

test('1. Adding a valid URL before session initialization succeeds', () => {
  const result = validateWebsiteSource('https://techcrunch.com/2026/solid-state-batteries')
  assert.equal(result.valid, true)
  assert.ok(result.source)
  assert.equal(result.source.type, 'website')
  assert.equal(result.source.url, 'https://techcrunch.com/2026/solid-state-batteries')
  assert.equal(result.source.status, 'pending')

  // Invalid URL validation
  const invalidResult = validateWebsiteSource('not-a-valid-url')
  assert.equal(invalidResult.valid, false)
  assert.match(invalidResult.error, /valid HTTP or HTTPS URL/)

  // Duplicate URL check
  const duplicateResult = validateWebsiteSource('https://techcrunch.com/2026/solid-state-batteries', [result.source])
  assert.equal(duplicateResult.valid, false)
  assert.match(duplicateResult.error, /already been added/)
})

test('2. Adding pasted text before session initialization succeeds', () => {
  const result = validatePastedTextSource({
    text: 'Transcript excerpt of laboratory test results indicating 98% cathode retention.',
    title: 'Lab Benchmark Test Excerpt',
  })
  assert.equal(result.valid, true)
  assert.ok(result.source)
  assert.equal(result.source.type, 'pasted_text')
  assert.equal(result.source.userTitle, 'Lab Benchmark Test Excerpt')
  assert.equal(result.source.charCount, 79)
  assert.equal(result.source.status, 'pending')

  // Empty pasted text validation
  const emptyResult = validatePastedTextSource({ text: '   ' })
  assert.equal(emptyResult.valid, false)
  assert.match(emptyResult.error, /must not be empty/)
})

test('3. Selecting PDF/DOCX files before session initialization succeeds with size and extension checks', () => {
  const validPdfFile = {
    name: 'battery-specs.pdf',
    size: 2 * 1024 * 1024, // 2 MB
  }
  const result = validateDocumentSource({ file: validPdfFile, title: 'Battery Spec Sheet' })
  assert.equal(result.valid, true)
  assert.ok(result.source)
  assert.equal(result.source.type, 'document')
  assert.equal(result.source.title, 'Battery Spec Sheet')
  assert.equal(result.source.status, 'pending')

  // Invalid extension (.txt)
  const invalidExtFile = { name: 'notes.txt', size: 1024 }
  const invalidExtResult = validateDocumentSource({ file: invalidExtFile })
  assert.equal(invalidExtResult.valid, false)
  assert.match(invalidExtResult.error, /Only PDF and DOCX files are supported/)

  // File size exceeding 10 MB limit
  const oversizedFile = { name: 'huge-data.pdf', size: 15 * 1024 * 1024 }
  const oversizedResult = validateDocumentSource({ file: oversizedFile })
  assert.equal(oversizedResult.valid, false)
  assert.match(oversizedResult.error, /exceeds the maximum allowable limit of 10 MB/)
})

test('4. Maximum five sources capacity is strictly enforced', () => {
  const existingSources = [
    { type: 'website', url: 'https://site1.com' },
    { type: 'website', url: 'https://site2.com' },
    { type: 'website', url: 'https://site3.com' },
    { type: 'website', url: 'https://site4.com' },
    { type: 'website', url: 'https://site5.com' },
  ]
  assert.equal(existingSources.length, MAX_SOURCES)

  const webResult = validateWebsiteSource('https://site6.com', existingSources)
  assert.equal(webResult.valid, false)
  assert.match(webResult.error, /Maximum of 5 sources allowed/)

  const textResult = validatePastedTextSource({ text: 'Some text' }, existingSources)
  assert.equal(textResult.valid, false)
  assert.match(textResult.error, /Maximum of 5 sources allowed/)

  const docResult = validateDocumentSource({ file: { name: 'test.pdf', size: 500 } }, existingSources)
  assert.equal(docResult.valid, false)
  assert.match(docResult.error, /Maximum of 5 sources allowed/)
})

test('5. Session creation followed by sequential source uploads succeeds', async () => {
  const createdSessions = []
  const uploadedWebsites = []
  const uploadedTexts = []
  const uploadedDocuments = []

  const mockCreateResearch = async ({ research_goal }) => {
    createdSessions.push(research_goal)
    return { data: { id: 'sess-uuid-1234' } }
  }

  const mockAddWebsite = async (sessionId, payload) => {
    uploadedWebsites.push({ sessionId, payload })
    return { success: true }
  }

  const mockAddText = async (sessionId, payload) => {
    uploadedTexts.push({ sessionId, payload })
    return { success: true }
  }

  const mockAddDoc = async (sessionId, payload) => {
    uploadedDocuments.push({ sessionId, payload })
    return { success: true }
  }

  const preparedSources = [
    { id: '1', type: 'website', url: 'https://nature.com/articles/s41586-battery', status: 'pending' },
    { id: '2', type: 'pasted_text', text: 'Pasted research notes', userTitle: 'Field Notes', status: 'pending' },
    { id: '3', type: 'document', file: { name: 'report.pdf', size: 1000 }, userTitle: 'Annual Report', status: 'pending' },
  ]

  const result = await executeSessionInitialization({
    researchGoal: 'Investigate battery tech breakthrough claims',
    preparedSources,
    createResearchFn: mockCreateResearch,
    addWebsiteSourceFn: mockAddWebsite,
    addPastedTextSourceFn: mockAddText,
    addDocumentSourceFn: mockAddDoc,
  })

  assert.equal(result.success, true)
  assert.equal(result.sessionId, 'sess-uuid-1234')
  assert.equal(createdSessions.length, 1)
  assert.equal(createdSessions[0], 'Investigate battery tech breakthrough claims')
  assert.equal(uploadedWebsites.length, 1)
  assert.equal(uploadedWebsites[0].sessionId, 'sess-uuid-1234')
  assert.equal(uploadedTexts.length, 1)
  assert.equal(uploadedTexts[0].payload.text, 'Pasted research notes')
  assert.equal(uploadedDocuments.length, 1)
  assert.equal(uploadedDocuments[0].payload.title, 'Annual Report')
  assert.equal(result.updatedSources.every((s) => s.status === 'success'), true)
})

test('6. Partial source-upload failure and retry preserves session without creating duplicate', async () => {
  let sessionCreationCalls = 0
  const mockCreateResearch = async () => {
    sessionCreationCalls++
    return { data: { id: 'sess-uuid-fixed' } }
  }

  let websiteAttempts = 0
  const mockAddWebsite = async () => {
    websiteAttempts++
    // First attempt fails, subsequent succeeds
    if (websiteAttempts === 1) {
      throw new Error('Connection timeout while extracting website.')
    }
    return { success: true }
  }

  let textAttempts = 0
  const mockAddText = async () => {
    textAttempts++
    return { success: true }
  }

  const preparedSources = [
    { id: 'src-web', type: 'website', url: 'https://flaky-site.org', status: 'pending' },
    { id: 'src-txt', type: 'pasted_text', text: 'Verified lab report', userTitle: 'Lab Report', status: 'pending' },
  ]

  // First execution: website fails, text succeeds
  const firstRun = await executeSessionInitialization({
    researchGoal: 'Investigate flaky site claims',
    preparedSources,
    activeSessionId: null,
    createResearchFn: mockCreateResearch,
    addWebsiteSourceFn: mockAddWebsite,
    addPastedTextSourceFn: mockAddText,
    addDocumentSourceFn: async () => {},
  })

  assert.equal(firstRun.success, false)
  assert.equal(firstRun.sessionId, 'sess-uuid-fixed')
  assert.equal(sessionCreationCalls, 1)
  assert.equal(firstRun.failedCount, 1)
  assert.equal(firstRun.updatedSources[0].status, 'failed')
  assert.match(firstRun.updatedSources[0].error, /Connection timeout/)
  assert.equal(firstRun.updatedSources[1].status, 'success')

  // Retry execution: passed activeSessionId and previous updatedSources
  const retryRun = await executeSessionInitialization({
    researchGoal: 'Investigate flaky site claims',
    preparedSources: firstRun.updatedSources,
    activeSessionId: firstRun.sessionId, // Preserves created session!
    createResearchFn: mockCreateResearch,
    addWebsiteSourceFn: mockAddWebsite,
    addPastedTextSourceFn: mockAddText,
    addDocumentSourceFn: async () => {},
  })

  // Verify createResearch was NOT called again!
  assert.equal(sessionCreationCalls, 1)
  // Verify already successful text source was NOT re-uploaded!
  assert.equal(textAttempts, 1)
  // Verify failed website was retried and now succeeded!
  assert.equal(websiteAttempts, 2)
  assert.equal(retryRun.success, true)
  assert.equal(retryRun.failedCount, 0)
  assert.equal(retryRun.updatedSources.every((s) => s.status === 'success'), true)
})

test('7. Removing a prepared source before initialization correctly updates queue and limits', () => {
  let sources = [
    { id: '1', type: 'website', url: 'https://site1.com' },
    { id: '2', type: 'website', url: 'https://site2.com' },
    { id: '3', type: 'pasted_text', text: 'Notes' },
  ]
  assert.equal(sources.length, 3)

  // Remove source with id '2'
  sources = sources.filter((s) => s.id !== '2')
  assert.equal(sources.length, 2)
  assert.equal(sources.some((s) => s.id === '2'), false)

  // Adding a new source now has capacity
  const newAdd = validateWebsiteSource('https://site4.com', sources)
  assert.equal(newAdd.valid, true)
})

test('8. Existing research session creation without prepared sources works directly', async () => {
  let created = false
  const mockCreateResearch = async () => {
    created = true
    return { data: { id: 'sess-empty-sources' } }
  }

  const result = await executeSessionInitialization({
    researchGoal: 'Zero sources exploration goal',
    preparedSources: [],
    createResearchFn: mockCreateResearch,
    addWebsiteSourceFn: async () => {},
    addPastedTextSourceFn: async () => {},
    addDocumentSourceFn: async () => {},
  })

  assert.equal(result.success, true)
  assert.equal(result.sessionId, 'sess-empty-sources')
  assert.equal(result.failedCount, 0)
  assert.equal(created, true)
})
