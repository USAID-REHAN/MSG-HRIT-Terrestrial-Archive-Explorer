import { GlobeWorkspace } from "@/components/GlobeWorkspace";

export default async function TimeslotGlobePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <GlobeWorkspace timeslotId={Number(id)} />;
}
