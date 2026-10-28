<script setup lang="ts">
// The woven x: an indigo stroke passing under a coral (exclude) stroke.
// The under-stroke is cut rather than haloed so the mark works on any surface.
withDefaults(defineProps<{ tight?: boolean }>(), { tight: false })
</script>

<template>
  <svg :viewBox="tight ? '9 9 30 30' : '0 0 48 48'" aria-hidden="true" focusable="false">
    <g class="fill-primary stroke-primary">
      <circle cx="13" cy="13" r="4" stroke="none" />
      <path d="M13 13L19.05 19.05" stroke-width="8" />
      <path d="M28.95 28.95L35 35" stroke-width="8" />
      <circle cx="35" cy="35" r="4" stroke="none" />
    </g>
    <path d="M35 13L13 35" class="stroke-exclude" stroke-width="8" stroke-linecap="round" fill="none" />
  </svg>
</template>
