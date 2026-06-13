// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC1155/ERC1155.sol";
import "@openzeppelin/contracts/token/ERC1155/extensions/ERC1155Supply.sol";
import "@openzeppelin/contracts/token/ERC721/utils/ERC721Holder.sol";
import "@openzeppelin/contracts/token/ERC721/IERC721.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title VoiceShares — 목소리 분할 토큰화 (fractional ownership)
/// @notice VoiceRegistry NFT(목소리 1개)를 금고에 잠그고, 그 목소리에 대한
///         ERC-1155 지분 토큰을 발행한다. 여러 명이 한 목소리를 분할 소유하며,
///         로열티(VOICE)를 지분 비례로 배당받는다. 100% 지분을 모으면 NFT를 되찾는다.
/// @dev voiceId == ERC-1155 token id == 해당 목소리의 지분. 배당은 누적 분배 모델
///      (accRewardPerShare)로 전송이 일어나도 정확히 정산된다. 테스트넷 프로토타입(미감사).
contract VoiceShares is ERC1155Supply, ERC721Holder, ReentrancyGuard {
    using SafeERC20 for IERC20;

    IERC20 public immutable token;       // 로열티 결제 통화 (VoiceCoin)
    IERC721 public immutable registry;   // VoiceRegistry NFT
    uint256 private constant ACC = 1e12; // 정밀도 스케일

    struct Vault { address curator; bool fractionalized; }
    mapping(uint256 => Vault) public vaults;                       // voiceId => 금고
    mapping(uint256 => uint256) public accRewardPerShare;          // voiceId => 누적 배당/지분
    mapping(uint256 => mapping(address => uint256)) public rewardDebt;
    mapping(uint256 => mapping(address => uint256)) public pendingReward;
    mapping(uint256 => uint256) public totalDistributed;           // voiceId 누적 배당총액

    event Fractionalized(uint256 indexed voiceId, address indexed curator, uint256 shares);
    event RoyaltyDeposited(uint256 indexed voiceId, address indexed from, uint256 amount);
    event Claimed(uint256 indexed voiceId, address indexed holder, uint256 amount);
    event Redeemed(uint256 indexed voiceId, address indexed redeemer);

    constructor(address token_, address registry_, string memory uri_) ERC1155(uri_) {
        require(token_ != address(0) && registry_ != address(0), "zero addr");
        token = IERC20(token_);
        registry = IERC721(registry_);
    }

    /// @notice 목소리를 분할 토큰화: NFT를 잠그고 `shares`개의 지분 토큰을 발행.
    /// @dev 호출 전 registry에서 이 컨트랙트에 approve/ setApprovalForAll 필요.
    function fractionalize(uint256 voiceId, uint256 shares) external nonReentrant {
        require(shares > 0, "shares=0");
        require(!vaults[voiceId].fractionalized, "already fractionalized");
        require(registry.ownerOf(voiceId) == msg.sender, "not voice owner");
        registry.safeTransferFrom(msg.sender, address(this), voiceId); // NFT 잠금
        vaults[voiceId] = Vault(msg.sender, true);
        _mint(msg.sender, voiceId, shares, "");
        emit Fractionalized(voiceId, msg.sender, shares);
    }

    /// @notice 해당 목소리의 로열티(VOICE)를 예치 → 지분 보유자에게 비례 배당.
    function depositRoyalty(uint256 voiceId, uint256 amount) external nonReentrant {
        require(vaults[voiceId].fractionalized, "not fractionalized");
        uint256 supply = totalSupply(voiceId);
        require(supply > 0, "no shares");
        require(amount > 0, "amount=0");
        token.safeTransferFrom(msg.sender, address(this), amount);
        accRewardPerShare[voiceId] += (amount * ACC) / supply;
        totalDistributed[voiceId] += amount;
        emit RoyaltyDeposited(voiceId, msg.sender, amount);
    }

    /// @notice 청구 가능한 배당 조회
    function pending(uint256 voiceId, address holder) public view returns (uint256) {
        uint256 bal = balanceOf(holder, voiceId);
        uint256 accrued = (bal * accRewardPerShare[voiceId]) / ACC;
        uint256 debt = rewardDebt[voiceId][holder];
        uint256 extra = accrued > debt ? accrued - debt : 0;
        return pendingReward[voiceId][holder] + extra;
    }

    /// @notice 누적 배당 청구
    function claim(uint256 voiceId) external nonReentrant {
        _settle(msg.sender, voiceId);
        uint256 amount = pendingReward[voiceId][msg.sender];
        require(amount > 0, "nothing to claim");
        pendingReward[voiceId][msg.sender] = 0;
        rewardDebt[voiceId][msg.sender] =
            (balanceOf(msg.sender, voiceId) * accRewardPerShare[voiceId]) / ACC;
        token.safeTransfer(msg.sender, amount);
        emit Claimed(voiceId, msg.sender, amount);
    }

    /// @notice 100% 지분 보유 시 지분 소각 후 NFT 회수(통합).
    function redeem(uint256 voiceId) external nonReentrant {
        require(vaults[voiceId].fractionalized, "not fractionalized");
        uint256 supply = totalSupply(voiceId);
        require(supply > 0 && balanceOf(msg.sender, voiceId) == supply, "need 100% shares");
        _settle(msg.sender, voiceId);
        _burn(msg.sender, voiceId, supply);
        vaults[voiceId].fractionalized = false;
        accRewardPerShare[voiceId] = 0;           // 다음 라운드를 위해 초기화
        rewardDebt[voiceId][msg.sender] = 0;
        registry.safeTransferFrom(address(this), msg.sender, voiceId);
        emit Redeemed(voiceId, msg.sender);
    }

    // ---- 내부 배당 정산 ----
    function _settle(address user, uint256 voiceId) internal {
        uint256 bal = balanceOf(user, voiceId);
        uint256 accrued = (bal * accRewardPerShare[voiceId]) / ACC;
        uint256 debt = rewardDebt[voiceId][user];
        if (accrued > debt) pendingReward[voiceId][user] += accrued - debt;
        rewardDebt[voiceId][user] = accrued;
    }

    /// @dev 지분 전송/발행/소각 시 보상 정산(전송돼도 배당이 정확히 따라가게).
    function _update(address from, address to, uint256[] memory ids, uint256[] memory values)
        internal override
    {
        if (from != address(0)) { for (uint256 i; i < ids.length; i++) _settle(from, ids[i]); }
        if (to != address(0))   { for (uint256 i; i < ids.length; i++) _settle(to, ids[i]); }
        super._update(from, to, ids, values);
        if (from != address(0)) {
            for (uint256 i; i < ids.length; i++)
                rewardDebt[ids[i]][from] = (balanceOf(from, ids[i]) * accRewardPerShare[ids[i]]) / ACC;
        }
        if (to != address(0)) {
            for (uint256 i; i < ids.length; i++)
                rewardDebt[ids[i]][to] = (balanceOf(to, ids[i]) * accRewardPerShare[ids[i]]) / ACC;
        }
    }
}
