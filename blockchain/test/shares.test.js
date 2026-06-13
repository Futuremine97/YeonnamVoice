const { expect } = require("chai");
const { ethers } = require("hardhat");

// 목소리 분할 토큰화: 분할발행 → 지분 전송 → 로열티 배당(지분비례) → 청구 → 100% redeem
describe("VoiceShares 분할 토큰화", function () {
  let coin, registry, shares;
  let owner, curator, investor, platform;
  const e18 = (n) => ethers.parseUnits(n.toString(), 18);

  beforeEach(async () => {
    [owner, curator, investor, platform] = await ethers.getSigners();

    const Coin = await ethers.getContractFactory("VoiceCoin");
    coin = await Coin.deploy(e18(1_000_000_000), e18(100_000_000), owner.address);

    const Registry = await ethers.getContractFactory("VoiceRegistry");
    registry = await Registry.deploy("ipfs://base/");

    const Shares = await ethers.getContractFactory("VoiceShares");
    shares = await Shares.deploy(await coin.getAddress(), await registry.getAddress(), "ipfs://shares/");

    // 큐레이터가 목소리 등록(동의 해시 포함)
    const consent = ethers.keccak256(ethers.toUtf8Bytes("consent-v1"));
    await registry.connect(curator).registerVoice(consent, "American", e18(100), e18(1), 8000);
    // 플랫폼에 배당 재원 지급
    await coin.transfer(platform.address, e18(1000));
  });

  it("분할 토큰화 → NFT 잠금 + 지분 발행", async () => {
    await registry.connect(curator).setApprovalForAll(await shares.getAddress(), true);
    await shares.connect(curator).fractionalize(1, 1000);
    expect(await registry.ownerOf(1)).to.equal(await shares.getAddress()); // NFT 잠김
    expect(await shares.balanceOf(curator.address, 1)).to.equal(1000n);
    expect(await shares.totalSupply(1)).to.equal(1000n);
  });

  it("지분 전송 + 로열티 지분비례 배당/청구", async () => {
    await registry.connect(curator).setApprovalForAll(await shares.getAddress(), true);
    await shares.connect(curator).fractionalize(1, 1000);
    // 투자자에게 400 지분 전송 (curator 600 / investor 400)
    await shares.connect(curator).safeTransferFrom(curator.address, investor.address, 1, 400, "0x");

    // 플랫폼이 100 VOICE 로열티 예치
    await coin.connect(platform).approve(await shares.getAddress(), e18(100));
    await shares.connect(platform).depositRoyalty(1, e18(100));

    // 지분 비례: curator 60, investor 40
    expect(await shares.pending(1, curator.address)).to.equal(e18(60));
    expect(await shares.pending(1, investor.address)).to.equal(e18(40));

    await shares.connect(investor).claim(1);
    expect(await coin.balanceOf(investor.address)).to.equal(e18(40));
    expect(await shares.pending(1, investor.address)).to.equal(0);
    // curator 청구 잔여 유지
    expect(await shares.pending(1, curator.address)).to.equal(e18(60));
  });

  it("전송 후 배당은 전송 시점 지분 기준으로 정확히 정산", async () => {
    await registry.connect(curator).setApprovalForAll(await shares.getAddress(), true);
    await shares.connect(curator).fractionalize(1, 1000);

    // 1차 배당(전송 전, curator 100%) → curator 100
    await coin.connect(platform).approve(await shares.getAddress(), e18(200));
    await shares.connect(platform).depositRoyalty(1, e18(100));
    // 이제 절반 전송
    await shares.connect(curator).safeTransferFrom(curator.address, investor.address, 1, 500, "0x");
    // 2차 배당(전송 후, 각 50%) → 각 50
    await shares.connect(platform).depositRoyalty(1, e18(100));

    expect(await shares.pending(1, curator.address)).to.equal(e18(150)); // 100 + 50
    expect(await shares.pending(1, investor.address)).to.equal(e18(50));  // 0 + 50
  });

  it("100% 지분 보유 시 redeem 으로 NFT 회수", async () => {
    await registry.connect(curator).setApprovalForAll(await shares.getAddress(), true);
    await shares.connect(curator).fractionalize(1, 1000);
    await shares.connect(curator).redeem(1);
    expect(await registry.ownerOf(1)).to.equal(curator.address);
    expect(await shares.totalSupply(1)).to.equal(0n);
  });
});
