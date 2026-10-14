// ------------------------------------------------------------
// Strud AI — API boundary
//
// All backend communication funnels through here. Components never
// call fetch() directly. The AI contract is deliberately model-
// agnostic: POST /api/chat decides retrieval/vision/model server-side.
// ------------------------------------------------------------

export { BACKEND_URL, ApiError, CONNECTION_ERROR } from "./errors";
export { sendMessage, generateTitle } from "./chat";
export { getChats, persistChats, createChat, fetchChats, persistTitle, fetchDeletedChats, moveChatToBin, restoreChat, permanentlyDeleteChat, emptyRecycleBin } from "./chats";
