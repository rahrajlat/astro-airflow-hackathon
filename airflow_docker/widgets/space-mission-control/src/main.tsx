import type { FC } from "react";
import { MissionDisplayPage } from "./pages/MissionDisplayPage";
import { MissionControlPage } from "./pages/MissionControlPage";
const SpaceMissionControl: FC = () => new URLSearchParams(window.location.search).get("display")==="5inch"?<MissionDisplayPage/>:<MissionControlPage />;
export default SpaceMissionControl;
