import { redirect } from "next/navigation";

export default function AuditReportRedirectPage({ params }: { params: { id: string } }) {
    redirect(`/report/${params.id}`);
}
