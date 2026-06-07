import { describe, expect, it } from 'vitest'

import { evalCaseRowSchema } from './schema'

describe('SWE-chat artifact schemas', () => {
  it('accepts dataset eval cases with chat-window I/A/P markers', () => {
    const parsed = evalCaseRowSchema.parse({
      case_id: 'session-1#4:correction',
      repo_id: 'owner/repo',
      session_id: 'session-1',
      session_created_at: '2026-06-06T00:00:00Z',
      repo_session_index: 8,
      eligible_prior_sessions: 7,
      user_id: null,
      agent: 'claude-code',
      checkpoint_pk: 'checkpoint-1',
      i_turn_id: 'turn-2',
      i_turn_number: 2,
      i_content: 'Please update the dataloader.',
      a_turn_id: 'turn-3',
      a_turn_number: 3,
      a_content: 'I changed the wrong module.',
      p_turn_id: 'turn-4',
      p_turn_number: 4,
      p_content: 'No, that is not the dataloader path.',
      prompt_intent: 'coding',
      prompt_pushback: 'correction',
      chat_window: [
        {
          turn_id: 'turn-2',
          turn_number: 2,
          role: 'user',
          turn_type: 'message',
          content: 'Please update the dataloader.',
          marker: 'I',
        },
        {
          turn_id: 'turn-3',
          turn_number: 3,
          role: 'assistant',
          turn_type: 'message',
          content: 'I changed the wrong module.',
          marker: 'A',
        },
        {
          turn_id: 'turn-4',
          turn_number: 4,
          role: 'user',
          turn_type: 'message',
          content: 'No, that is not the dataloader path.',
          marker: 'P',
        },
      ],
    })

    expect(parsed.chat_window).toHaveLength(3)
    expect(parsed.chat_window?.map((turn) => turn.marker)).toEqual([
      'I',
      'A',
      'P',
    ])
  })
})
