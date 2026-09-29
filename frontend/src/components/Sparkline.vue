<template>
  <div>
    <svg viewBox="0 0 300 90" class="spark" preserveAspectRatio="none">
      <defs>
        <linearGradient id="sparkFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#FF0000" stop-opacity="0.18" />
          <stop offset="100%" stop-color="#FF0000" stop-opacity="0" />
        </linearGradient>
      </defs>
      <polygon :points="areaPoints" fill="url(#sparkFill)" />
      <polyline :points="linePoints" fill="none" stroke="#FF0000" stroke-width="2"
                stroke-linecap="round" stroke-linejoin="round" />
      <circle :cx="lastPoint.x" :cy="lastPoint.y" r="3" fill="#FF0000" />
    </svg>
    <div class="spread mono" style="font-size:12px">
      <span class="muted">day low {{ low }}</span>
      <span>{{ from }}/{{to}}</span>
      <span class="muted">day high {{ high }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ rate: number; from: string; to: string; series?: number[] }>()

const series = computed(() => {
  if (props.series && props.series.length > 1) {
    return [...props.series.slice(0, -1), props.rate]  // live point on top
  }
  const base = props.rate || 1
  const pts: number[] = []
  let x = 12345
  for (let i = 0; i < 40; i++) {
    x = (1103515245 * x + 12345) % 2147483648
    const noise = ((x / 2147483648) - 0.5) * 0.02
    pts.push(base * (1 + noise))
  }
  pts[pts.length - 1] = base
  return pts
})

const linePoints = computed(() => {
  const s = series.value
  const min = Math.min(...s)
  const max = Math.max(...s)
  const span = max - min || 1
  return s.map((v, i) => {
    const x = (i / (s.length - 1)) * 296 + 2
    const y = 84 - ((v - min) / span) * 72
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
})

const areaPoints = computed(() => `2,88 ${linePoints.value} 298,88`)

const lastPoint = computed(() => {
  const parts = linePoints.value.split(' ')
  const [x, y] = parts[parts.length - 1].split(',')
  return { x: Number(x), y: Number(y) }
})

const low = computed(() => Math.min(...series.value).toFixed(4))
const high = computed(() => Math.max(...series.value).toFixed(4))
</script>

<style scoped>
.spark { width: 100%; height: 110px; display: block; }
</style>
