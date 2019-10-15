"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.

"""

import click
from web3 import Web3

from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import IndividualAllocationRegistry
from nucypher.blockchain.eth.token import NU
from nucypher.blockchain.eth.utils import datetime_at_period
from nucypher.characters.lawful import StakeHolder
from nucypher.cli import painting, actions
from nucypher.cli.actions import (
    confirm_staged_stake,
    get_client_password,
    select_stake,
    confirm_enable_restaking_lock,
    confirm_enable_restaking,
    handle_client_account_for_staking,
)
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.painting import paint_receipt_summary
from nucypher.cli.types import (
    EIP55_CHECKSUM_ADDRESS,
    EXISTING_READABLE_FILE
)
from nucypher.config.characters import StakeHolderConfiguration


@click.command()
@click.argument('action')
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
@click.option('--force', help="Don't ask for confirmation", is_flag=True)
@click.option('--hw-wallet/--no-hw-wallet', default=False)  # TODO: Make True or deprecate.
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--poa', help="Inject POA middleware", is_flag=True)
@click.option('--provider', 'provider_uri', help="Blockchain provider's URI i.e. 'file:///path/to/geth.ipc'", type=click.STRING)
@click.option('--staking-address', help="Address to stake NU tokens", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--worker-address', help="Address to assign as an Ursula-Worker", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--staking-reward/--no-staking-reward', is_flag=True, default=False)
@click.option('--policy-reward/--no-policy-reward', is_flag=True, default=False)
@click.option('--withdraw-address', help="Send reward collection to an alternate address", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--value', help="Token value of stake", type=click.INT)
@click.option('--lock-periods', help="Duration of stake in periods.", type=click.INT)
@click.option('--index', help="A specific stake index to resume", type=click.INT)
@click.option('--enable/--disable', help="Used to enable and disable re-staking", is_flag=True, default=True)
@click.option('--lock-until', help="Period to release re-staking lock", type=click.IntRange(min=0))
@click.option('--beneficiary-address', help="Address of a pre-allocation beneficiary", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--allocation-filepath', help="Path to individual allocation file", type=EXISTING_READABLE_FILE)
@nucypher_click_config
def stake(click_config,
          action,

          config_root,
          config_file,

          # Mode
          force,
          hw_wallet,

          # Blockchain
          poa,
          registry_filepath,
          provider_uri,

          # Stake
          staking_address,
          worker_address,
          withdraw_address,
          value,
          lock_periods,
          index,
          policy_reward,
          staking_reward,
          enable,
          lock_until,

          # Allocation stakers
          beneficiary_address,
          allocation_filepath,
          ) -> None:
    """
    Manage stakes and other staker-related operations.

    \b
    Actions
    -------------------------------------------------
    init-stakeholder  Create a new stakeholder configuration
    list              List active stakes for current stakeholder
    accounts          Show ETH and NU balances for stakeholder's accounts
    sync              Synchronize stake data with on-chain information
    set-worker        Bond a worker to a staker
    detach-worker     Detach worker currently bonded to a staker
    init              Create a new stake
    restake           Manage re-staking with --enable or --disable
    divide            Create a new stake from part of an existing one
    collect-reward    Withdraw staking reward

    """

    # Banner
    emitter = click_config.emitter
    emitter.clear()
    emitter.banner(StakeHolder.banner)

    if action == 'init-stakeholder':

        if not provider_uri:
            raise click.BadOptionUsage(option_name='--provider',
                                       message="--provider is required to create a new stakeholder.")

        new_stakeholder = StakeHolderConfiguration.generate(config_root=config_root,
                                                            provider_uri=provider_uri,
                                                            poa=poa,
                                                            sync=False,
                                                            registry_filepath=registry_filepath)

        filepath = new_stakeholder.to_configuration_file(override=force)
        emitter.echo(f"Wrote new stakeholder configuration to {filepath}", color='green')
        return  # Exit

    try:
        stakeholder_config = StakeHolderConfiguration.from_configuration_file(filepath=config_file,
                                                                              provider_uri=provider_uri,
                                                                              poa=poa,
                                                                              sync=False,
                                                                              registry_filepath=registry_filepath)
    except FileNotFoundError:
        return actions.handle_missing_configuration_file(character_config_class=StakeHolderConfiguration,
                                                         config_file=config_file)

    #
    # Make Stakeholder
    #

    # First let's check whether we're dealing here with a regular staker or a preallocation staker
    is_preallocation_staker = (beneficiary_address and staking_address) or allocation_filepath

    if is_preallocation_staker:
        if allocation_filepath:
            if beneficiary_address or staking_address:
                message = "--allocation-filepath is incompatible with --beneficiary-address and --staking-address."
                raise click.BadOptionUsage(option_name="--allocation-filepath", message=message)

            # This assumes the user has an individual allocation file in disk
            individual_allocation = IndividualAllocationRegistry.from_allocation_file(allocation_filepath)
            initial_address = individual_allocation.beneficiary_address
        elif beneficiary_address and staking_address:
            individual_allocation = IndividualAllocationRegistry(beneficiary_address=beneficiary_address,
                                                                 contract_address=staking_address)
            initial_address = beneficiary_address
        else:
            option = "--beneficiary_address" if beneficiary_address else "--staking-address"
            raise click.BadOptionUsage(option_name=option,
                                       message=f"You must specify both --beneficiary-address and --staking-address. "
                                               f"Only {option} was provided. As an alternative, you can simply "
                                               f"provide an individual allocation with --allocation-file <PATH>")
    else:
        individual_allocation = None
        initial_address = staking_address

    STAKEHOLDER = stakeholder_config.produce(initial_address=initial_address,
                                             individual_allocation=individual_allocation)
    blockchain = BlockchainInterfaceFactory.get_interface(provider_uri=provider_uri)  # Eager connection

    economics = STAKEHOLDER.economics

    # Dynamic click types (Economics)
    min_locked = economics.minimum_allowed_locked
    stake_value_range = click.FloatRange(min=NU.from_nunits(min_locked).to_tokens(), clamp=False)
    stake_duration_range = click.IntRange(min=economics.minimum_locked_periods, clamp=False)
    stake_extension_range = click.IntRange(min=1, max=economics.maximum_allowed_locked, clamp=False)

    #
    # Eager Actions
    #

    if action == 'list':
        stakes = STAKEHOLDER.all_stakes
        if not stakes:
            emitter.echo(f"There are no active stakes")
        else:
            painting.paint_stakes(emitter=emitter, stakes=stakes)
        return  # Exit

    elif action == 'accounts':
        # TODO: Order accounts like shown by blockchain.client.accounts
        for address, balances in STAKEHOLDER.wallet.balances.items():
            emitter.echo(f"{address} | {Web3.fromWei(balances['ETH'], 'ether')} ETH | {NU.from_nunits(balances['NU'])}")
        return  # Exit

    elif action == 'set-worker':

        client_account, staking_address = handle_client_account_for_staking(emitter=emitter,
                                                                            stakeholder=STAKEHOLDER,
                                                                            staking_address=staking_address,
                                                                            individual_allocation=individual_allocation,
                                                                            force=force)

        if not worker_address:
            worker_address = click.prompt("Enter worker address", type=EIP55_CHECKSUM_ADDRESS)

        # TODO: Check preconditions (e.g., minWorkerPeriods, already in use, etc)

        password = None
        if not hw_wallet and not blockchain.client.is_local:
            password = get_client_password(checksum_address=client_account)

        STAKEHOLDER.assimilate(checksum_address=client_account, password=password)
        receipt = STAKEHOLDER.set_worker(worker_address=worker_address)

        # TODO: Double-check dates
        current_period = STAKEHOLDER.staking_agent.get_current_period()
        bonded_date = datetime_at_period(period=current_period, seconds_per_period=economics.seconds_per_period)
        min_worker_periods = STAKEHOLDER.staking_agent.staking_parameters()[7]
        release_period = current_period + min_worker_periods
        release_date = datetime_at_period(period=release_period, seconds_per_period=economics.seconds_per_period)

        emitter.echo(f"\nWorker {worker_address} successfully bonded to staker {staking_address}", color='green')
        paint_receipt_summary(emitter=emitter,
                              receipt=receipt,
                              chain_name=blockchain.client.chain_name,
                              transaction_type='set_worker')
        emitter.echo(f"Bonded at period #{current_period} ({bonded_date})", color='green')
        emitter.echo(f"This worker can be replaced or detached after period "
                     f"#{release_period} ({release_date})", color='green')
        return  # Exit

    elif action == 'detach-worker':

        client_account, staking_address = handle_client_account_for_staking(emitter=emitter,
                                                                            stakeholder=STAKEHOLDER,
                                                                            staking_address=staking_address,
                                                                            individual_allocation=individual_allocation,
                                                                            force=force)

        if worker_address:
            raise click.BadOptionUsage(message="detach-worker cannot be used together with --worker-address",
                                       option_name='--worker-address')

        # TODO: Check preconditions (e.g., minWorkerPeriods)

        worker_address = STAKEHOLDER.staking_agent.get_worker_from_staker(staking_address)

        password = None
        if not hw_wallet and not blockchain.client.is_local:
            password = get_client_password(checksum_address=client_account)

        STAKEHOLDER.assimilate(checksum_address=client_account, password=password)
        receipt = STAKEHOLDER.detach_worker()

        # TODO: Double-check dates
        current_period = STAKEHOLDER.staking_agent.get_current_period()
        bonded_date = datetime_at_period(period=current_period, seconds_per_period=economics.seconds_per_period)

        emitter.echo(f"Successfully detached worker {worker_address} from staker {staking_address}", color='green')
        paint_receipt_summary(emitter=emitter,
                              receipt=receipt,
                              chain_name=blockchain.client.chain_name,
                              transaction_type='detach_worker')
        emitter.echo(f"Detached at period #{current_period} ({bonded_date})", color='green')
        return  # Exit

    elif action == 'create':
        """Create a new stake"""

        #
        # Get Staking Account
        #

        client_account, staking_address = handle_client_account_for_staking(emitter=emitter,
                                                                            stakeholder=STAKEHOLDER,
                                                                            staking_address=staking_address,
                                                                            individual_allocation=individual_allocation,
                                                                            force=force)

        password = None
        if not hw_wallet and not blockchain.client.is_local:
            password = get_client_password(checksum_address=client_account)

        #
        # Stage Stake
        #

        if not value:
            value = click.prompt(f"Enter stake value in NU",
                                 type=stake_value_range,
                                 default=NU.from_nunits(min_locked).to_tokens())
        value = NU.from_tokens(value)

        if not lock_periods:
            prompt = f"Enter stake duration ({STAKEHOLDER.economics.minimum_locked_periods} periods minimum)"
            lock_periods = click.prompt(prompt, type=stake_duration_range)

        start_period = STAKEHOLDER.staking_agent.get_current_period()
        end_period = start_period + lock_periods

        #
        # Review
        #

        if not force:
            painting.paint_staged_stake(emitter=emitter,
                                        stakeholder=STAKEHOLDER,
                                        staking_address=staking_address,
                                        stake_value=value,
                                        lock_periods=lock_periods,
                                        start_period=start_period,
                                        end_period=end_period)

            confirm_staged_stake(staker_address=staking_address, value=value, lock_periods=lock_periods)

        # Last chance to bail
        click.confirm("Publish staged stake to the blockchain?", abort=True)

        # Execute
        STAKEHOLDER.assimilate(checksum_address=client_account, password=password)
        new_stake = STAKEHOLDER.initialize_stake(amount=value, lock_periods=lock_periods)

        painting.paint_staking_confirmation(emitter=emitter,
                                            ursula=STAKEHOLDER,
                                            transactions=new_stake.transactions)
        return  # Exit

    elif action == "restake":

        # Authenticate
        client_account, staking_address = handle_client_account_for_staking(emitter=emitter,
                                                                            stakeholder=STAKEHOLDER,
                                                                            staking_address=staking_address,
                                                                            individual_allocation=individual_allocation,
                                                                            force=force)

        password = None
        if not hw_wallet and not blockchain.client.is_local:
            password = get_client_password(checksum_address=client_account)
        STAKEHOLDER.assimilate(checksum_address=client_account, password=password)

        # Inner Exclusive Switch
        if lock_until:
            if not force:
                confirm_enable_restaking_lock(emitter, staking_address=staking_address, release_period=lock_until)
            receipt = STAKEHOLDER.enable_restaking_lock(release_period=lock_until)
            emitter.echo(f'Successfully enabled re-staking lock for {staking_address} until {lock_until}',
                         color='green', verbosity=1)
        elif enable:
            if not force:
                confirm_enable_restaking(emitter, staking_address=staking_address)
            receipt = STAKEHOLDER.enable_restaking()
            emitter.echo(f'Successfully enabled re-staking for {staking_address}', color='green', verbosity=1)
        else:
            if not force:
                click.confirm(f"Confirm disable re-staking for staker {staking_address}?", abort=True)
            receipt = STAKEHOLDER.disable_restaking()
            emitter.echo(f'Successfully disabled re-staking for {staking_address}', color='green', verbosity=1)

        paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=blockchain.client.chain_name)
        return  # Exit

    elif action == 'divide':
        """Divide an existing stake by specifying the new target value and end period"""

        if staking_address and index is not None:  # 0 is valid.
            current_stake = STAKEHOLDER.stakes[index]
        else:
            current_stake = select_stake(stakeholder=STAKEHOLDER, emitter=emitter)

        #
        # Stage Stake
        #

        # Value
        if not value:
            value = click.prompt(f"Enter target value (must be less than or equal to {str(current_stake.value)})",
                                 type=stake_value_range)
        value = NU(value, 'NU')

        # Duration
        if not lock_periods:
            extension = click.prompt("Enter number of periods to extend", type=stake_extension_range)
        else:
            extension = lock_periods

        if not force:
            painting.paint_staged_stake_division(emitter=emitter,
                                                 stakeholder=STAKEHOLDER,
                                                 original_stake=current_stake,
                                                 target_value=value,
                                                 extension=extension)
            click.confirm("Is this correct?", abort=True)

        # Execute
        password = None
        if not hw_wallet and not blockchain.client.is_local:
            password = get_client_password(checksum_address=current_stake.staker_address)

        STAKEHOLDER.assimilate(checksum_address=current_stake.staker_address, password=password)
        modified_stake, new_stake = STAKEHOLDER.divide_stake(stake_index=current_stake.index,
                                                             target_value=value,
                                                             additional_periods=extension)
        emitter.echo('Successfully divided stake', color='green', verbosity=1)
        paint_receipt_summary(emitter=emitter,
                              receipt=new_stake.receipt,
                              chain_name=blockchain.client.chain_name)

        # Show the resulting stake list
        painting.paint_stakes(emitter=emitter, stakes=STAKEHOLDER.stakes)
        return  # Exit

    elif action == 'collect-reward':
        """Withdraw staking reward to the specified wallet address"""

        # Authenticate
        client_account, staking_address = handle_client_account_for_staking(emitter=emitter,
                                                                            stakeholder=STAKEHOLDER,
                                                                            staking_address=staking_address,
                                                                            individual_allocation=individual_allocation,
                                                                            force=force)

        password = None
        if not hw_wallet and not blockchain.client.is_local:
            password = get_client_password(checksum_address=client_account)

        if not staking_reward and not policy_reward:
            raise click.BadArgumentUsage(f"Either --staking-reward or --policy-reward must be True to collect rewards.")

        STAKEHOLDER.assimilate(checksum_address=client_account, password=password)
        if staking_reward:
            # Note: Sending staking / inflation rewards to another account is not allowed.
            staking_receipt = STAKEHOLDER.collect_staking_reward()
            paint_receipt_summary(receipt=staking_receipt,
                                  chain_name=STAKEHOLDER.wallet.blockchain.client.chain_name,
                                  emitter=emitter)

        if policy_reward:
            policy_receipt = STAKEHOLDER.collect_policy_reward(collector_address=withdraw_address)
            paint_receipt_summary(receipt=policy_receipt,
                                  chain_name=STAKEHOLDER.wallet.blockchain.client.chain_name,
                                  emitter=emitter)

        return  # Exit

    # TODO: Action "mint"
    
    # Catch-All for unknown actions
    else:
        ctx = click.get_current_context()
        raise click.UsageError(message=f"Unknown action '{action}'.", ctx=ctx)

