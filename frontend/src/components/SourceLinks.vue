<template>
  <div v-if="sources.length" class="source-list" aria-label="sources">
    <a
      v-for="(source, index) in sources"
      :key="`${source.url}-${index}`"
      class="source-chip"
      :href="source.url"
      target="_blank"
      rel="noopener noreferrer"
      :title="source.snippet || source.title"
    >
      src{{ index + 1 }}
    </a>
  </div>
</template>

<script setup>
defineProps({
  sources: {
    type: Array,
    default: () => [],
  },
})
</script>

<style scoped>
.source-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.source-chip {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  color: #0f5f96;
  background: #e3f0fb;
  border: 1px solid #bfd9ee;
  text-decoration: none;
}

.source-chip:hover {
  background: #d6e9f8;
  border-color: #a7cde8;
}
</style>
