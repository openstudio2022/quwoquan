include(ExternalProject)

set(ZIPFILE "${CMAKE_CURRENT_LIST_DIR}/downloads/libwebrtc.zip")
set(EXTRACT_DIR "${CMAKE_CURRENT_LIST_DIR}/libwebrtc")

if(NOT EXISTS "${ZIPFILE}")
  message(FATAL_ERROR
    "Missing vendored libwebrtc archive at ${ZIPFILE}. "
    "This repository forbids build-time remote downloads; stage the pinned archive explicitly before enabling desktop WebRTC builds."
  )
else()
  if(NOT EXISTS "${EXTRACT_DIR}")
    message(NOTICE "libwebrtc directory does not exist after extraction.")
    file(ARCHIVE_EXTRACT INPUT ${ZIPFILE} DESTINATION "${CMAKE_CURRENT_LIST_DIR}")
  endif()
  message(TRACE "Using vendored libwebrtc archive.")
endif()
