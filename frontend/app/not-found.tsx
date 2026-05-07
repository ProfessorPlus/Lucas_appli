import Link from "next/link";
import { Compass, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-secondary text-muted-foreground">
        <Compass className="h-8 w-8" />
      </div>
      <h1 className="text-2xl font-bold">Page introuvable</h1>
      <p className="max-w-md text-sm text-muted-foreground">
        Cette page n'existe pas (encore). Si tu cherches une feature de l'ancien Streamlit,
        elle sera migrée dans les prochaines étapes.
      </p>
      <Button asChild>
        <Link href="/">
          <ArrowLeft /> Retour à l'accueil
        </Link>
      </Button>
    </div>
  );
}
