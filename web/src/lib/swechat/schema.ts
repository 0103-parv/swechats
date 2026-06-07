import { z } from 'zod'

const nullableString = z.string().nullable()
const artifactString = z.string().min(1)
const artifactInt = z.number().int()

export type ArtifactKind = 'eval-cases' | 'candidate-pushbacks'

const chatWindowTurnSchema = z
  .object({
    turn_id: artifactString,
    turn_number: artifactInt,
    role: artifactString,
    turn_type: artifactString,
    content: artifactString,
    prompt_intent: nullableString.optional(),
    prompt_pushback: nullableString.optional(),
    marker: z.enum(['I', 'A', 'P']).nullable().optional(),
  })
  .passthrough()

export const evalCaseRowSchema = z
  .object({
    case_id: artifactString,
    repo_id: artifactString,
    session_id: artifactString,
    session_created_at: artifactString,
    repo_session_index: artifactInt,
    eligible_prior_sessions: artifactInt,
    user_id: nullableString,
    agent: artifactString,
    checkpoint_pk: artifactString,
    i_turn_id: artifactString,
    i_turn_number: artifactInt,
    i_content: artifactString,
    a_turn_id: artifactString,
    a_turn_number: artifactInt,
    a_content: artifactString,
    p_turn_id: artifactString,
    p_turn_number: artifactInt,
    p_content: artifactString,
    prompt_intent: artifactString,
    prompt_pushback: artifactString,
    chat_window: z.array(chatWindowTurnSchema).optional(),
  })
  .passthrough()

export const candidatePushbackRowSchema = z
  .object({
    repo_id: artifactString,
    session_id: artifactString,
    turn_id: artifactString,
    checkpoint_pk: artifactString,
    turn_number: artifactInt,
    conversation_turn_number: z.number(),
    role: artifactString,
    turn_type: artifactString,
    content: artifactString,
    prompt_intent: artifactString,
    prompt_pushback: artifactString,
    timestamp: nullableString,
  })
  .passthrough()

export type RawEvalCaseRow = z.infer<typeof evalCaseRowSchema>
export type RawCandidatePushbackRow = z.infer<typeof candidatePushbackRowSchema>
