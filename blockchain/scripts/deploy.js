// VoiceCoin 생태계 배포 스크립트
// 실행: npx hardhat run scripts/deploy.js  (로컬) / --network sepolia (테스트넷)
const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deployer:", deployer.address);

  const e18 = (n) => hre.ethers.parseUnits(n.toString(), 18);

  // 1) VoiceCoin (상한 10억, 초기 1억 트레저리)
  const Coin = await hre.ethers.getContractFactory("VoiceCoin");
  const coin = await Coin.deploy(e18(1_000_000_000), e18(100_000_000), deployer.address);
  await coin.waitForDeployment();
  console.log("VoiceCoin:", await coin.getAddress());

  // 2) VoiceRegistry (소유권/동의 NFT)
  const Registry = await hre.ethers.getContractFactory("VoiceRegistry");
  const registry = await Registry.deploy("https://api.englishforus.example/voice/");
  await registry.waitForDeployment();
  console.log("VoiceRegistry:", await registry.getAddress());

  // 3) VoiceLicense (결제/로열티)
  const License = await hre.ethers.getContractFactory("VoiceLicense");
  const license = await License.deploy(
    await coin.getAddress(),
    await registry.getAddress(),
    deployer.address // treasury
  );
  await license.waitForDeployment();
  console.log("VoiceLicense:", await license.getAddress());

  // 4) VoiceStaking (스테이킹/거버넌스, 제안 최소 스테이크 1000 VOICE)
  const Staking = await hre.ethers.getContractFactory("VoiceStaking");
  const staking = await Staking.deploy(await coin.getAddress(), e18(1000));
  await staking.waitForDeployment();
  console.log("VoiceStaking:", await staking.getAddress());

  // License 가 보상 발행할 수 있도록 민터 권한(선택)
  await (await coin.setMinter(await license.getAddress(), true)).wait();

  console.log("\n배포 완료. 주소를 프론트/백엔드 설정에 기록하세요.");
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
