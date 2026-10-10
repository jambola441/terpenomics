import { ScrollView, Text, View } from 'react-native'
import { router } from 'expo-router'
import { api } from '@/lib/api'
import { useFetch } from '@/lib/useFetch'
import { Button, FeedState, Label, styles } from '@/components/ui'
import { PointsSteps } from '@/components/partners'
import { PARTNER_DEFINITION, questions } from '@web/utils/pointsProgram'
import { t, space, font, type } from '@/lib/theme'

/** The points program in three steps and a few questions, from the API's own
 *  numbers. Same words as the web's /portal/how-points-work. */
export default function HowPointsWork() {
  const { data, error, loading, refresh } = useFetch('partners', () => api.portal.getPartners())
  if (loading || !data) return <FeedState loading={loading} error={error} onRetry={refresh} />
  const program = data.program

  return (
    <ScrollView style={styles.screen} contentContainerStyle={{ padding: space[4], paddingBottom: space[8] }}>
      <Text style={[type.copy, { color: t.text3, marginBottom: space[5] }]}>{PARTNER_DEFINITION}</Text>
      <PointsSteps program={program} />
      <Button title="See partner stores" icon="pin" onPress={() => router.push('/partners')} style={{ marginTop: space[6] }} />

      <Label style={{ marginTop: space[7], marginBottom: space[1] }}>Questions</Label>
      {questions(program).map(item => (
        <View key={item.q} style={{ paddingVertical: space[4], borderBottomWidth: 1, borderBottomColor: t.border }}>
          <Text style={[type.bodyStrong, { fontSize: font.size.callout }]}>{item.q}</Text>
          <Text style={[type.copy, { marginTop: 4 }]}>{item.a}</Text>
        </View>
      ))}
    </ScrollView>
  )
}
